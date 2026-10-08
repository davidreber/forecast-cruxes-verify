#!/usr/bin/bash
#SBATCH --partition=general,veitch
#SBATCH --job-name=verify_tests
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16GB
#SBATCH --time=01:00:00
#SBATCH --exclude=m001,m002
#SBATCH --kill-on-invalid-dep=yes
#SBATCH --output=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_tests_%j.out
#SBATCH --error=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_tests_%j.err
#
# Cost: $0. CPU only. Runs both test suites: the package's and this
# repository's. Neither loads a model or reads Data/.

source /net/projects/veitch/forecast-cruxes/forecast-cruxes-verify/scripts/authors_cluster/common.sh

echo "== package tests"
cd "${PACKAGE_DIR}"
PYTHONPATH="${PACKAGE_DIR}/src" python -u -m pytest -p no:cacheprovider -q -rs ${PYTEST_ARGS:-} tests
package_status=$?

echo "== verification repository tests"
cd "${VERIFY_DIR}"
PYTHONPATH="${PACKAGE_DIR}/src:${VERIFY_DIR}/src" python -u -m pytest -p no:cacheprovider -q -rs ${PYTEST_ARGS:-} tests
verify_status=$?

echo "package tests exit ${package_status}, verification tests exit ${verify_status}"
exit $(( package_status || verify_status ))
