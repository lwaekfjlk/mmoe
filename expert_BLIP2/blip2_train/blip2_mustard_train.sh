python train.py \
--dataset mustard \
--train_path ../../mustard_data/data_split_output/mustard_AS_dataset_train.json \
--val_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--test_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--image_data_path ../../mustard_data/data_raw/images \
--save_path ./blip2_mustard_AS_model;

python train.py \
--dataset mustard \
--train_path ../../mustard_data/data_split_output/mustard_R_dataset_train.json \
--val_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--test_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--image_data_path ../../mustard_data/data_raw/images \
--save_path ./blip2_mustard_R_model;

python train.py \
--dataset mustard \
--train_path ../../mustard_data/data_split_output/mustard_U_dataset_train.json \
--val_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--test_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--image_data_path ../../mustard_data/data_raw/images \
--save_path ./blip2_mustard_U_model;

python train.py \
--dataset mustard \
--train_path ../../mustard_data/data_split_output/mustard_dataset_train.json \
--val_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--test_path ../../mustard_data/data_split_output/mustard_dataset_test.json \
--image_data_path ../../mustard_data/data_raw/images \
--save_path ./blip2_mustard_baseline_model;