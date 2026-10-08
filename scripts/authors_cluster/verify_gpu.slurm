#!/usr/bin/bash
#SBATCH --partition=general,veitch
#SBATCH --job-name=verify_gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64GB
#SBATCH --gres=gpu:1
#SBATCH --constraint="a100|h100|h200"
#SBATCH --time=08:00:00
#SBATCH --array=0-9
#SBATCH --exclude=m001,m002
#SBATCH --kill-on-invalid-dep=yes
#SBATCH --output=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_gpu_%A_%a.out
#SBATCH --error=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_gpu_%A_%a.err
#
# Cost: $0. One local GPU per task, the pinned 8B reranker, no API.
#
# The reviewer's GPU stage: the package's cruxes-score for one run per array
# task. Tasks 0 to 5 are the six runs at 25 premises a side (about 2.5 hours
# each for March Madness on an A100). The run at 50 a side scores four times
# the prompts per question (about 10 hours in one piece), so tasks 6 to 9 each
# score every fourth of its questions. Caches go to the work directory; a
# cache is never overwritten, so the tasks can share it.

source /net/projects/veitch/forecast-cruxes/forecast-cruxes-verify/scripts/authors_cluster/common.sh
set -eo pipefail

RUNS=(
    march_madness/resolution
    march_madness/equivalence
    march_madness/debate
    metaculus/resolution
    metaculus/equivalence
    metaculus/debate
    "march_madness/resolution@50 --array-task-id 0 --num-array-tasks 4"
    "march_madness/resolution@50 --array-task-id 1 --num-array-tasks 4"
    "march_madness/resolution@50 --array-task-id 2 --num-array-tasks 4"
    "march_madness/resolution@50 --array-task-id 3 --num-array-tasks 4"
)
RUN=${RUNS[${SLURM_ARRAY_TASK_ID}]}
echo "run:     ${RUN}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

"${VENV}/bin/cruxes-verify" score --artifact "${ARTIFACT}" --work-dir "${WORK}" --run ${RUN}
