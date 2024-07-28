import json
import torch
from torch.utils.data import Dataset, DataLoader
from PIL import Image


class URFUNNYDataset(Dataset):
    def __init__(self, split, image_data_path, tokenizer, image_processor, max_length=512):
        if split == "train":
            dataset_files = {
                "R": "../urfunny_data/data_split_output/urfunny_R_dataset_train_cogvlm2_qwen2.json",
                "U": "../urfunny_data/data_split_output/urfunny_U_dataset_train_cogvlm2_qwen2.json",
                "S": "../urfunny_data/data_split_output/urfunny_AS_dataset_train_cogvlm2_qwen2.json",
            }
        elif split == "val":
            dataset_files = {
                "R": "../urfunny_data/data_split_output/urfunny_R_dataset_val_cogvlm2_qwen2.json",
                "U": "../urfunny_data/data_split_output/urfunny_U_dataset_val_cogvlm2_qwen2.json",
                "S": "../urfunny_data/data_split_output/urfunny_AS_dataset_val_cogvlm2_qwen2.json",
            }
        elif split == "test":
            dataset_files = {
                "R": "../urfunny_data/data_split_output/urfunny_R_dataset_test_cogvlm2_qwen2.json",
                "U": "../urfunny_data/data_split_output/urfunny_U_dataset_test_cogvlm2_qwen2.json",
                "S": "../urfunny_data/data_split_output/urfunny_AS_dataset_test_cogvlm2_qwen2.json",
            }
        self.dataset = self.load_dataset(dataset_files)
        self.tokenizer = tokenizer
        self.image_processor = image_processor
        self.image_data_path = image_data_path
        self.max_length = max_length

    def load_dataset(self, dataset_files):
        overall_dataset = []
        label_map = {"R": 0, "U": 1, "S": 2}
        
        for type, file_path in dataset_files.items():
            with open(file_path) as f:
                data = json.load(f)
            for id, content in data.items():
                overall_dataset.append({
                    "id": id,
                    "image_id": id,
                    "text": content["punchline_sentence"],
                    "label": label_map[type]
                })
        return overall_dataset

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        item = self.dataset[idx]
        image_path = f'{self.image_data_path}/{item["image_id"]}.png'
        image = self.image_processor(Image.open(image_path), return_tensors="pt").pixel_values.squeeze(0)
        label = torch.tensor(item['label'], dtype=torch.long)
        text_encoding = self.tokenizer(f"The tweet related to this image is: {item['text']}.", 
                                       truncation=True, 
                                       max_length=self.max_length, 
                                       return_tensors="pt",
                                       padding='max_length')
        
        return { 
            "input_ids": text_encoding["input_ids"].squeeze(),
            "attention_mask": text_encoding["attention_mask"].squeeze(),
            "image": image,
            "label": label,
            "id": item["id"],
        }

def urfunny_collate(batch):
    return {
        "input_ids": torch.stack([item["input_ids"] for item in batch]),
        "attention_mask": torch.stack([item["attention_mask"] for item in batch]),
        "image": torch.stack([item["image"] for item in batch]),
        "label": torch.stack([item["label"] for item in batch]),
        "id": [item["id"] for item in batch],
    }

def get_urfunny_dataloader(args, tokenizer, image_processor, split):
    if split == "train":
        dataset = URFUNNYDataset(split, args.image_data_path, tokenizer, image_processor, args.max_length)
        return DataLoader(dataset, batch_size=args.batch_size, shuffle=True, collate_fn=urfunny_collate)
    elif split == "val":
        dataset = URFUNNYDataset(split, args.image_data_path, tokenizer, image_processor, args.max_length)
        return DataLoader(dataset, batch_size=args.val_batch_size, shuffle=False, collate_fn=urfunny_collate)
    elif split == "test":
        dataset = URFUNNYDataset(split, args.image_data_path, tokenizer, image_processor, args.max_length)
        return DataLoader(dataset, batch_size=args.test_batch_size, shuffle=False, collate_fn=urfunny_collate)
