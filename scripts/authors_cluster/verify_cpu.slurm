#!/usr/bin/bash
#SBATCH --partition=general,veitch
#SBATCH --job-name=verify_cpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32GB
#SBATCH --time=04:00:00
#SBATCH --exclude=m001,m002
#SBATCH --kill-on-invalid-dep=yes
#SBATCH --output=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_cpu_%j.out
#SBATCH --error=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_cpu_%j.err
#
# Cost: $0. CPU only.
#
# The reviewer's CPU stage and the verdict: cruxes-report and each listed
# analysis for every run, then the comparison with the paper's numbers (the
# verifier's expected numbers), with the authors' recorded scores for the raw
# score check, then the paper's figures redrawn from the rerun.
#
#   sbatch --export=ALL,VERIFY_ARGS="--run metaculus/resolution" scripts/authors_cluster/verify_cpu.slurm
#
# restricts report and compare to some runs (and skips the figures).

source /net/projects/veitch/forecast-cruxes/forecast-cruxes-verify/scripts/authors_cluster/common.sh

"${VENV}/bin/cruxes-verify" report --artifact "${ARTIFACT}" --work-dir "${WORK}" ${VERIFY_ARGS:-} || exit 1
"${VENV}/bin/cruxes-verify" compare --artifact "${ARTIFACT}" --work-dir "${WORK}" --recorded-scores "${PROVENANCE}/scores" ${VERIFY_ARGS:-}
status=$?
if [ -z "${VERIFY_ARGS:-}" ]; then
    "${VENV}/bin/python" -m cruxes_verify.figures.render --work-dir "${WORK}" || echo "figures failed"
fi
echo "verify exit status ${status}"
exit ${status}
