#!/bin/bash
#SBATCH --job-name=evac-bengkulu
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=32
#SBATCH --time=00:30:00
#SBATCH --partition=compute        # SESUAIKAN dengan nama partisi cluster Anda
#SBATCH --account=PROJECT_ID       # SESUAIKAN dengan ID proyek/alokasi
#SBATCH --output=slurm-%j.out

# Modul bersifat spesifik per cluster; cek dengan `module avail`.
module load python mpi
source .venv/bin/activate          # python -m venv .venv && pip install -r requirements.txt mpi4py

srun python -m evac.sweep --backend mpi --reps 20 --out results/results_mpi.csv
