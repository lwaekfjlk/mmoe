import numpy as np
from collections import defaultdict
import os
import jsonlines

def load_and_transform_data(file_dir):
    subset_names = ['AS', 'R', 'U']
    dataset = defaultdict(list)
    results = defaultdict(lambda: {'logits': defaultdict(list), 'target': None})

    # Load data from files
    for name in subset_names:
        file_path = os.path.join(file_dir, f'sarc_vision_text_label_test_{name}.jsonl')
        with jsonlines.open(file_path, 'r') as f:
            for line in f:
                image_id = line['image_id']
                text = line['text']
                data_id = f"{image_id}_{text}"
                dataset[name].append(line)
                results[data_id]['logits'][name] = line['logits']
                if results[data_id]['target'] is None:
                    results[data_id]['target'] = line['target']
                assert results[data_id]['target'] == line['target'], "Targets do not match across subsets for the same data."
    return dataset, results

def interaction_type_acc(results, interaction_type='AS'):
    correct = 0
    for data_id, data in results.items():
        total_logits = data['logits'][interaction_type]
        predicted_label = total_logits.index(max(total_logits))
        if predicted_label == data['target']:
            correct += 1
    return correct / len(results)

def simple_average_fusion(results):
    correct = 0
    for data_id, data in results.items():
        total_logits = [sum(logits) / len(logits) for logits in zip(*data['logits'].values())]
        predicted_label = total_logits.index(max(total_logits))
        if predicted_label == data['target']:
            correct += 1
    return correct / len(results)

def weighted_average_fusion(results, weights):
    correct = 0
    for data_id, data in results.items():
        weighted_logits = [sum(w * logits[i] for w, logits in zip(weights, data['logits'].values()))
                           for i in range(len(next(iter(data['logits'].values()))))]
        predicted_label = weighted_logits.index(max(weighted_logits))
        if predicted_label == data['target']:
            correct += 1
    return correct / len(results)

def max_fusion(results):
    correct = 0
    for data_id, data in results.items():
        max_logits = [max(logits) for logits in zip(*data['logits'].values())]
        predicted_label = max_logits.index(max(max_logits))
        if predicted_label == data['target']:
            correct += 1
    return correct / len(results)

def softmax_fusion(results):
    correct = 0
    for data_id, data in results.items():
        softmaxed_probs = [np.exp(logits) / np.sum(np.exp(logits)) for logits in data['logits'].values()]
        average_probs = np.mean(softmaxed_probs, axis=0)
        predicted_label = np.argmax(average_probs)
        if predicted_label == data['target']:
            correct += 1
    return correct / len(results)

def cascaded_fusion(results, threshold):
    correct = 0
    for data_id, data in results.items():
        softmaxed_probs = {}
        for interaction_type, logits in data['logits'].items():
            softmaxed_probs[interaction_type] = np.exp(logits) / np.sum(np.exp(logits))
        if np.max(softmaxed_probs['R']) > threshold and np.max(softmaxed_probs['U']) > threshold:
            predicted_label = np.argmax(softmaxed_probs['R']) if np.max(softmaxed_probs['R']) > np.max(softmaxed_probs['U']) else np.argmax(softmaxed_probs['U'])
        else:
            predicted_label = np.argmax(softmaxed_probs['AS'])
        if predicted_label == data['target']:
            correct += 1
    return correct / len(results)


# Example usage within your main workflow
if __name__ == "__main__":
    file_dir = '../../sarc_data/intermediate_data/ALBEF_RUS_outputs'
    _, transformed_results = load_and_transform_data(file_dir)

    weights = {'AS': 0.5, 'R': 0.3, 'U': 0.2}
    weighted_weights = [weights[name] for name in ['AS', 'R', 'U']]

    print("Simple Average Fusion Accuracy:", simple_average_fusion(transformed_results))
    print("Weighted Average Fusion Accuracy:", weighted_average_fusion(transformed_results, weighted_weights))
    print("Max Fusion Accuracy:", max_fusion(transformed_results))
    print("Softmax Fusion Accuracy:", softmax_fusion(transformed_results))
    for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
        print(f"Cascaded Fusion Accuracy (Threshold={threshold}):", cascaded_fusion(transformed_results, threshold))
    print("AS Interaction Type Accuracy:", interaction_type_acc(transformed_results, 'AS'))
    print("R Interaction Type Accuracy:", interaction_type_acc(transformed_results, 'R'))
    print("U Interaction Type Accuracy:", interaction_type_acc(transformed_results, 'U'))