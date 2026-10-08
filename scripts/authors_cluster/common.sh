# Shared settings of the cluster jobs. Sourced, not run.
#
# The reviewer installs two things into a fresh environment: the package, from
# its directory until it is on PyPI, and this repository. Nothing else of the
# authors' is on the path. The environment is a venv on scratch that borrows
# numpy, scipy, torch and transformers from the lab's conda environment, so no
# download is needed on a compute node.
#
# ARTIFACT is the data release (inputs only). PROVENANCE holds the authors'
# recorded scores, which are never part of the release; only the authors'
# comparison reads them.

source /net/projects/veitch/reber/miniconda3/etc/profile.d/conda.sh
conda activate pycrux

export PACKAGE_DIR=/net/projects/veitch/forecast-cruxes/cruxes-refactor-proposal-4/pkg
export VERIFY_DIR=/net/projects/veitch/forecast-cruxes/forecast-cruxes-verify
export VENV=/net/scratch2/reber/venvs/forecast_cruxes_proposal4
export ARTIFACT=/net/projects/veitch/forecast-cruxes/Data/runs/refactor_proposal_4_release
export PROVENANCE=/net/projects/veitch/forecast-cruxes/Data/runs/refactor_proposal_4_provenance
export WORK=/net/projects/veitch/forecast-cruxes/Data/runs/refactor_proposal_4_verify_run

export HF_HOME=/net/scratch2/reber/transformers_cache
export HF_HUB_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1

echo "host:    $(hostname)"
echo "package: $(git -C "${PACKAGE_DIR}" rev-parse --abbrev-ref HEAD) $(git -C "${PACKAGE_DIR}" rev-parse --short HEAD)"
echo "verify:  $(git -C "${VERIFY_DIR}" rev-parse --abbrev-ref HEAD) $(git -C "${VERIFY_DIR}" rev-parse --short HEAD 2>/dev/null || echo uncommitted)"
