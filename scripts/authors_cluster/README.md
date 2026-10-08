# The authors' cluster jobs

Authors' cluster only. These Slurm jobs are the record of how
`VERIFICATION.md` was produced; they are kept for audit, not for reuse. The
paths, partitions, node exclusions and the lab conda environment (`pycrux`)
are site specific, and they will not run anywhere else as they stand. To
verify the paper on your own machine, follow the repository's README.

| file | what it ran |
|---|---|
| `common.sh` | shared settings, sourced by every job: the lab conda environment, the checkout and output paths, the Hugging Face cache, offline mode |
| `build_artifact.slurm` | CPU: builds the data release and the recorded scores with `artifact_builder/build_release.py`, makes a venv, installs the package and this repository, then `check`, `prepare` and a dry run of `score` |
| `verify_gpu.slurm` | GPU, ten array tasks: `score` for the six runs at 25 a side (tasks 0 to 5) and the run at 50 a side in four slices (tasks 6 to 9) |
| `verify_cpu.slurm` | CPU: `report`, `compare` with the recorded scores, and the figures |
| `run_tests.slurm` | CPU: the package's test suite and this repository's |

Software versions. The venv is made with `--system-site-packages` on top of
the lab conda environment, which supplies numpy, scipy, torch and
transformers, so their versions are those of that environment at run time;
they are not pinned here. The package and this repository were installed
from local checkouts, whose branch and commit every job prints first (see
`common.sh`).

Each job sources `common.sh` by its absolute path on the cluster
(`/net/projects/veitch/forecast-cruxes/forecast-cruxes-verify/scripts/authors_cluster/common.sh`),
not relative to the job script, because `sbatch` runs a spooled copy of the
script, so `$(dirname "$0")` does not point at this directory.
