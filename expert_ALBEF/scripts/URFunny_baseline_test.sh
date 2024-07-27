python -m torch.distributed.launch --nproc_per_node=5 --use_env URFunny.py \
--config ./configs/URFunny_test.yaml \
--output_dir ./output/URFunny \
--checkpoint ./output/URFunny/checkpoint_best.pth \
--no-train