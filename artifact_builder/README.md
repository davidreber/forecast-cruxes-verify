# artifact_builder: how the release and the expected numbers were derived

Provenance only. These programs read the authors' internal runs on their
cluster and cannot run anywhere else. They are kept so that a reader can audit
how the data release and the verifier's expected numbers were derived from
those runs; nothing here is needed to verify the paper.

| file | what it does |
|---|---|
| `build_release.py` | builds the data release (inputs only) and, with `--provenance-out`, the recorded reranker scores, from the internal runs, read only; it checks the package's removal of repeated premises against the counts the paper reports before it writes anything |
| `build_expected.py` | writes `src/cruxes_verify/expected/`: the numbers the paper prints, converted to the package's names, and the two sample runs per dataset that the tolerances are measured from |
| `legacy.py` | the research code's premise selection and the conversion of its result files, used by both builders |
| `resolve_metaculus_post_ids.py` | looks up each Metaculus question's post id through the API and fills `metaculus_post_ids.json` |
| `metaculus_post_ids.json` | the authors' copy of the post ids, copied into the release as `datasets/metaculus/metaculus_post_ids.json` |

The internal files they read are recorded, each with its SHA-256, in
`src/cruxes_verify/expected/SOURCES.json` (the expected numbers) and in the
data release's `MANIFEST.json` under `internal_sources` (the release; each
dataset's `dataset.json` lists them too). Those paths are on the authors'
cluster and are not shipped.

`cruxes-verify` never imports anything here, and a test asserts that no
verifier module mentions these programs or any internal path. The Slurm job
that ran `build_release.py` for the release is
`scripts/authors_cluster/build_artifact.slurm`.
