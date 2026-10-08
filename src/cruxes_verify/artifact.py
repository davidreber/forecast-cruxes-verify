"""Reading a data release, and refusing one whose files are not what it says.

The release's layout is specified in ``docs/DATA_RELEASE_SPEC.md``. It holds
inputs only: the premises the models produced, the forecasts they came from,
the outcomes and the matching criteria. The paper's numbers are not in it;
they are results, and the verifier carries them itself (``expected.py``).

This module is the only code in the verifier that opens release files, and it
opens nothing else: no path of the authors' internal layout appears anywhere
in the verifier.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

__all__ = ["Artifact", "ArtifactError", "SPEC_VERSION"]

#: The layout version this verifier reads.
SPEC_VERSION = 2


class ArtifactError(ValueError):
    """The release is incomplete or its files do not match its manifest."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


#: Directories a reader's own tools write inside a release after it was
#: built, which the manifest cannot list: the Metaculus fetch script's default
#: output (``datasets/<dataset>/metaculus_fetched/``).
READER_WRITTEN_DIRECTORIES = ("metaculus_fetched",)


def _written_by_the_reader(relative: str) -> bool:
    parts = relative.split("/")
    if parts[0].startswith("."):
        # A git clone's ``.git/`` and similar tool directories are not release files.
        return True
    return len(parts) > 3 and parts[0] == "datasets" and parts[2] in READER_WRITTEN_DIRECTORIES


class Artifact:
    """A data release directory."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        manifest = self.root / "MANIFEST.json"
        if not manifest.is_file():
            raise ArtifactError(f"{self.root} has no MANIFEST.json; is it a data release?")
        self.manifest = self._load(manifest)
        version = self.manifest.get("spec_version")
        if version != SPEC_VERSION:
            raise ArtifactError(
                f"{self.root} is laid out by spec version {version}; this verifier reads "
                f"version {SPEC_VERSION} (docs/DATA_RELEASE_SPEC.md)"
            )

    @staticmethod
    def _load(path: Path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def load(self, relative: str):
        path = self.root / relative
        if not path.is_file():
            raise ArtifactError(f"the release has no {relative}")
        return self._load(path)

    def check_manifest(self) -> dict:
        """Hash every listed file; raise on a missing, changed or unlisted file.

        Files under ``datasets/<dataset>/metaculus_fetched/`` are the reader's
        own, written by the fetch script after the build, and are not checked;
        neither is anything under a top level directory whose name starts with
        a dot, such as the ``.git/`` of a clone of the release repository.
        """
        listed = self.manifest["files"]
        problems = []
        for relative, entry in listed.items():
            path = self.root / relative
            if not path.is_file():
                problems.append(f"missing: {relative}")
            elif _sha256(path) != entry["sha256"]:
                problems.append(f"changed: {relative}")
        present = {
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and p.name != "MANIFEST.json"
        }
        present = {r for r in present if not _written_by_the_reader(r)}
        problems += [f"not in the manifest: {r}" for r in sorted(present - set(listed))]
        if problems:
            raise ArtifactError(
                f"{len(problems)} manifest problems, first ones: {problems[:10]}"
            )
        return {"files": len(listed), "status": self.manifest.get("release_status")}

    def criteria(self) -> dict:
        """{name: criterion record}, in the file's order."""
        data = self.load("method/matching_criteria.json")
        return {c["name"]: c for c in data["criteria"]}

    def primary_criterion(self) -> str:
        return self.load("method/matching_criteria.json")["primary"]

    def datasets(self) -> list:
        return sorted(p.name for p in (self.root / "datasets").iterdir() if p.is_dir())

    def dataset(self, name: str) -> dict:
        return self.load(f"datasets/{name}/dataset.json")

    def pools(self, dataset: str, noise_reference: bool = False) -> tuple:
        """``(introspected, extracted)`` as produced, repeats kept.

        With ``noise_reference`` the introspected pools are the dataset's
        independent second sample.
        """
        base = f"datasets/{dataset}/"
        introspected = self.load(
            base + ("noise_reference/introspected.json" if noise_reference else "introspected.json")
        )
        return introspected, self.load(base + "extracted.json")
