#!/usr/bin/env bash
# seedrun.sh : jalankan seed penuh (±35 menit) pada DB kl2_t (salinan template kl2_m) di latar belakang.
# Pakai:  PYTHONHASHSEED=0 setsid nohup scripts/sandbox/seedrun.sh >/dev/null 2>&1 < /dev/null &   lalu pantau $B/full.out dan $B/seed_t.txt
. $(dirname $0)/env.sh
cd $B
echo "seed start $(date +%T)" > full.out
oshell -d kl2_t --no-http < /mnt/scripts/provision/run_seed.py > seed_t.txt 2>&1
echo "seed done rc=$? $(date +%T)" >> full.out
