#!/usr/bin/bash
#SBATCH --partition=general,veitch
#SBATCH --job-name=verify_build
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64GB
#SBATCH --time=02:00:00
#SBATCH --exclude=m001,m002
#SBATCH --kill-on-invalid-dep=yes
#SBATCH --output=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_build_%j.out
#SBATCH --error=/net/projects/veitch/forecast-cruxes/slurm_logs/verify_build_%j.err
#
# Cost: $0. CPU only, no model, no API.
#
# 1. Authors' side: build the data release (inputs only) and the internal
#    provenance (recorded scores) from our runs, read only, into two
#    directories that must not exist yet. The build checks the package's
#    removal of repeated premises against the paper's counts and the research
#    code's deduplicated pools before it writes anything.
# 2. Reviewer's side: make a fresh venv, install the package and this
#    repository into it, check the release's manifest, prepare the inputs and
#    plan the GPU work.

source /net/projects/veitch/forecast-cruxes/forecast-cruxes-verify/scripts/authors_cluster/common.sh
set -eo pipefail

cd "${VERIFY_DIR}"
PYTHONPATH="${PACKAGE_DIR}/src" python -u artifact_builder/build_release.py --out "${ARTIFACT}" --provenance-out "${PROVENANCE}"

python -m venv --system-site-packages "${VENV}"
"${VENV}/bin/pip" install --no-deps --no-build-isolation --no-index -e "${PACKAGE_DIR}" -e "${VERIFY_DIR}"
"${VENV}/bin/python" -c "import cruxes, cruxes_verify, sys; print('installed', cruxes.__file__, cruxes_verify.__file__); assert 'torch' not in sys.modules"

"${VENV}/bin/cruxes-verify" check --artifact "${ARTIFACT}"
"${VENV}/bin/cruxes-verify" prepare --artifact "${ARTIFACT}" --work-dir "${WORK}"
"${VENV}/bin/cruxes-verify" score --artifact "${ARTIFACT}" --work-dir "${WORK}" --dry-run
