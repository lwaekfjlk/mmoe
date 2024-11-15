import argparse
import json
import random

import numpy as np
import torch
import torch.nn as nn
from mmsd import get_mmsd_dataloader
from mustard import get_mustard_dataloader
from peft import LoraConfig, PeftModel, get_peft_model
from sklearn.metrics import f1_score, precision_score, recall_score
from tqdm import tqdm
from transformers import (AutoProcessor, AutoTokenizer,
                          Blip2ForConditionalGeneration)
from urfunny import get_urfunny_dataloader


class FocalLoss(nn.Module):
    def __init__(self, alpha=1, gamma=2, reduction="mean"):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, inputs, targets):
        BCE_loss = nn.functional.cross_entropy(inputs, targets, reduction="none")
        pt = torch.exp(-BCE_loss)
        F_loss = self.alpha * (1 - pt) ** self.gamma * BCE_loss

        if self.reduction == "mean":
            return torch.mean(F_loss)
        elif self.reduction == "sum":
            return torch.sum(F_loss)
        else:
            return F_loss


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)  # if you are using multi-GPU.
    # This ensures that CUDA operations are deterministic
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def evaluate(tokenizer, model, dataloader, device, args):
    model.eval()
    total_correct = 0
    total = 0
    total_yesno_logits = {}
    all_labels = []
    all_predictions = []
    yes_token_id = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("yes"))[0]
    no_token_id = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("no"))[0]
    other_token_id = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("other"))[0]

    for batch in tqdm(dataloader, desc="Evaluating", leave=False):
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        images = batch["image"].to(device)
        labels = batch["label"].to(device)
        ids = batch["id"]

        with torch.no_grad():
            outputs = model(
                input_ids=input_ids, attention_mask=attention_mask, pixel_values=images
            )
            logits = outputs.logits
            logits = logits[:, -1, :]

            yesno_logits = torch.stack(
                [
                    logits[:, no_token_id],
                    logits[:, yes_token_id],
                    logits[:, other_token_id],
                ],
                dim=-1,
            )
            predictions = torch.argmax(yesno_logits[:, :2], dim=-1)
            total_correct += (predictions == labels).sum().item()
            total += labels.size(0)
            yesno_logits = yesno_logits.tolist()
            for i, id in enumerate(ids):
                total_yesno_logits[id] = yesno_logits[i]
            all_labels.extend(labels.cpu().tolist())
            all_predictions.extend(predictions.cpu().tolist())

    accuracy = total_correct / total
    f1 = f1_score(all_labels, all_predictions)
    precision = precision_score(all_labels, all_predictions)
    recall = recall_score(all_labels, all_predictions)

    return accuracy, f1, precision, recall, total_yesno_logits


def train(model, train_dataloader, val_dataloader, tokenizer, device, args):
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    criterion = FocalLoss(alpha=0.25, gamma=2)

    yes_token_id = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("yes"))[0]
    no_token_id = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("no"))[0]
    other_token_id = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("other"))[0]

    best_f1 = -1
    model.train()

    acc, f1, precision, recall, yesno_logits = evaluate(
        tokenizer, model, val_dataloader, device, args
    )
    # model.save_pretrained(args.save_path)
    # with open(f"{args.save_path}/val_best_f1_yesno_logits.json", "w") as f:
    #    json.dump(yesno_logits, f)
    print("Starting point")
    print(f"Validation Accuracy: {acc:.4f}")
    print(f"Validation F1 Score: {f1:.4f}")
    print(f"Validation Precision: {precision:.4f}")
    print(f"Validation Recall: {recall:.4f}")

    total_step = 0
    for epoch in range(args.epochs):
        total_loss = 0

        for step, batch in enumerate(
            tqdm(train_dataloader, desc=f"Epoch {epoch + 1}", leave=False)
        ):
            total_step += 1
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            images = batch["image"].to(device)
            labels = batch["label"].to(device)

            optimizer.zero_grad()
            outputs = model(
                input_ids=input_ids, attention_mask=attention_mask, pixel_values=images
            )
            logits = outputs.logits[:, -1, :]
            yesno_logits = torch.stack(
                [
                    logits[:, no_token_id],
                    logits[:, yes_token_id],
                    logits[:, other_token_id],
                ],
                dim=-1,
            )
            loss = criterion(yesno_logits, labels)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

            if (total_step + 1) % args.eval_steps == 0:
                acc, f1, precision, recall, yesno_logits = evaluate(
                    tokenizer, model, val_dataloader, device, args
                )
                print(f"Epoch {epoch + 1} Step {step + 1}")
                print(f"Validation Accuracy: {acc:.4f}")
                print(f"Validation F1 Score: {f1:.4f}")
                print(f"Validation Precision: {precision:.4f}")
                print(f"Validation Recall: {recall:.4f}")

                if f1 >= best_f1:
                    best_f1 = f1
                    model.save_pretrained(args.save_path)
                    print("Model saved")
                    with open(
                        f"{args.save_path}/val_best_f1_yesno_logits.json", "w"
                    ) as f:
                        json.dump(yesno_logits, f)


def create_dataset_configs(dataset_names, dataset_paths, image_data_paths, max_lengths):
    configs = []
    for name, path, image_path, max_length in zip(
        dataset_names, dataset_paths, image_data_paths, max_lengths
    ):
        config = {
            "name": name,
            "dataset_path": path,
            "image_data_path": image_path,
            "max_length": max_length,
        }
        configs.append(config)
    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train a model on the mustard dataset")
    parser.add_argument(
        "--mode", type=str, default="train", help="Mode to run the script in"
    )
    parser.add_argument("--dataset", type=str, default="mustard")
    parser.add_argument(
        "--train_path",
        type=str,
        default="../mustard_data/data_split_output/mustard_AS_dataset_train.json",
        help="Path to the training data",
    )
    parser.add_argument(
        "--val_path",
        type=str,
        default="../mustard_data/data_split_output/mustard_dataset_test.json",
        help="Path to the validation data",
    )
    parser.add_argument(
        "--test_path",
        type=str,
        default="../mustard_data/data_split_output/mustard_dataset_test.json",
        help="Path to the test data",
    )
    parser.add_argument(
        "--image_data_path",
        type=str,
        default="../mustard_data/data_raw/images",
        help="Path to the image data",
    )
    parser.add_argument(
        "--batch_size", type=int, default=2, help="Batch size for training"
    )
    parser.add_argument(
        "--val_batch_size", type=int, default=32, help="Batch size for validation"
    )
    parser.add_argument(
        "--test_batch_size", type=int, default=32, help="Batch size for testing"
    )
    parser.add_argument(
        "--max_length",
        type=int,
        default=128,
        help="Maximum length for tokenized sequences",
    )
    parser.add_argument(
        "--epochs", type=int, default=50, help="Number of training epochs"
    )
    parser.add_argument("--lr", type=float, default=5e-5, help="Learning rate")
    parser.add_argument(
        "--eval_steps", type=int, default=10, help="Number of steps between evaluations"
    )
    parser.add_argument("--lora_r", type=int, default=16, help="LoRA r parameter")
    parser.add_argument(
        "--lora_alpha", type=int, default=32, help="LoRA alpha parameter"
    )
    parser.add_argument(
        "--lora_dropout", type=float, default=0.05, help="LoRA dropout parameter"
    )
    parser.add_argument(
        "--save_path",
        type=str,
        default="./model",
        help="Path to save the trained model",
    )
    parser.add_argument(
        "--combined_dataset_names",
        type=str,
        nargs="+",
        default=[],
        help="Names of the datasets to combine",
    )
    parser.add_argument(
        "--combined_train_paths",
        type=str,
        nargs="+",
        default=[],
        help="Paths to the training data",
    )
    parser.add_argument(
        "--combined_val_paths",
        type=str,
        nargs="+",
        default=[],
        help="Paths to the validation data",
    )
    parser.add_argument(
        "--combined_test_paths",
        type=str,
        nargs="+",
        default=[],
        help="Paths to the test data",
    )
    parser.add_argument(
        "--combined_image_data_paths",
        type=str,
        nargs="+",
        default=[],
        help="Paths to the image data",
    )
    parser.add_argument(
        "--combined_max_lengths",
        type=int,
        nargs="+",
        default=[],
        help="Maximum lengths for tokenized sequences",
    )
    parser.add_argument(
        "--test_dataset", type=str, default="mustard", help="Dataset to test on"
    )
    parser.add_argument(
        "--load_model_name",
        type=str,
        default="./model",
        help="Path to load the model from",
    )
    parser.add_argument(
        "--load_from_ckpt", type=str, default=None, help="Path to load the model from"
    )
    parser.add_argument(
        "--seed", type=int, default=1234, help="Random seed for initialization"
    )  # Add seed argument

    args = parser.parse_args()

    set_seed(args.seed)

    # BLIP2 Properties
    tokenizer = AutoTokenizer.from_pretrained("Salesforce/blip2-opt-2.7b")
    processor = AutoProcessor.from_pretrained("Salesforce/blip2-opt-2.7b")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    if args.mode == "train":
        model = Blip2ForConditionalGeneration.from_pretrained(
            "Salesforce/blip2-opt-2.7b"
        )

        if args.load_from_ckpt:
            model = PeftModel.from_pretrained(
                model, args.load_from_ckpt, is_trainable=True
            )
        else:
            config = LoraConfig(
                r=args.lora_r,
                lora_alpha=args.lora_alpha,
                lora_dropout=args.lora_dropout,
                bias="none",
                target_modules=["q_proj", "k_proj"],
            )
            model = get_peft_model(model, config)

        model.print_trainable_parameters()
        model.to(device)

        if args.dataset == "mustard":
            train_dataloader = get_mustard_dataloader(
                args, tokenizer, processor, split="train"
            )
            val_dataloader = get_mustard_dataloader(
                args, tokenizer, processor, split="val"
            )
            test_dataloader = get_mustard_dataloader(
                args, tokenizer, processor, split="test"
            )
        elif args.dataset == "mmsd":
            train_dataloader = get_mmsd_dataloader(
                args, tokenizer, processor, split="train"
            )
            val_dataloader = get_mmsd_dataloader(
                args, tokenizer, processor, split="val"
            )
            test_dataloader = get_mmsd_dataloader(
                args, tokenizer, processor, split="test"
            )
        elif args.dataset == "urfunny":
            train_dataloader = get_urfunny_dataloader(
                args, tokenizer, processor, split="train"
            )
            val_dataloader = get_urfunny_dataloader(
                args, tokenizer, processor, split="val"
            )
            test_dataloader = get_urfunny_dataloader(
                args, tokenizer, processor, split="test"
            )

        train(model, train_dataloader, val_dataloader, tokenizer, device, args)

        model = PeftModel.from_pretrained(model, args.save_path, is_trainable=True).to(
            device
        )
        acc, f1, precision, recall, yesno_logits = evaluate(
            tokenizer, model, test_dataloader, device, args
        )
        print("Test Results:")
        print(f"Test Accuracy: {acc:.4f}")
        print(f"Test F1 Score: {f1:.4f}")
        print(f"Test Precision: {precision:.4f}")
        print(f"Test Recall: {recall:.4f}")

    elif args.mode == "test":
        model = Blip2ForConditionalGeneration.from_pretrained(
            "Salesforce/blip2-opt-2.7b"
        )
        model = PeftModel.from_pretrained(
            model, args.load_model_name, is_trainable=True
        ).to(device)

        if args.test_dataset == "mustard":
            test_dataloader = get_mustard_dataloader(
                args, tokenizer, processor, split="test"
            )
            acc, f1, precision, recall, yesno_logits = evaluate(
                tokenizer, model, test_dataloader, device, args
            )
            with open(f"./{args.load_model_name}/test_yesno_logits.json", "w") as f:
                json.dump(yesno_logits, f)
            print(acc, f1, precision, recall)

        elif args.test_dataset == "mmsd":
            test_dataloader = get_mmsd_dataloader(
                args, tokenizer, processor, split="test"
            )
            acc, f1, precision, recall, yesno_logits = evaluate(
                tokenizer, model, test_dataloader, device, args
            )

        elif args.test_dataset == "mmsd":
            test_dataloader = get_mmsd_dataloader(
                args, tokenizer, processor, split="test"
            )
            acc, f1, precision, recall, yesno_logits = evaluate(
                tokenizer, model, test_dataloader, device, args
            )
            with open(f"./{args.load_model_name}/test_yesno_logits.json", "w") as f:
                json.dump(yesno_logits, f)
            print(acc, f1, precision, recall)

        elif args.test_dataset == "urfunny":
            test_dataloader = get_urfunny_dataloader(
                args, tokenizer, processor, split="test"
            )
            acc, f1, precision, recall, yesno_logits = evaluate(
                tokenizer, model, test_dataloader, device, args
            )
            with open(f"./{args.load_model_name}/test_yesno_logits.json", "w") as f:
                json.dump(yesno_logits, f)
            print(acc, f1, precision, recall)
