"""``python -m cruxes_verify`` is the same as the ``cruxes-verify`` command."""

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
