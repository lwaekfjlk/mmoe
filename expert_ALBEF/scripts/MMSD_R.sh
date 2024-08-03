python -m torch.distributed.launch --nproc_per_node=6 --use_env MMSD.py \
--config ./configs/MMSD_R.yaml \
--output_dir ./output/MMSD-R \
--checkpoint ./ALBEF.pth \
--train
# > ./sarc-detect.log
# -m torch.distributed.launch --nproc_per_node=8 --use_env