"""Figure scripts for the paper, matplotlib only.

Each module is a standalone command line script that reads one of the JSON
files the verification's report step writes and produces a PNG at three
hundred dots per inch. They import nothing from the rest of the package, so a
change to the method cannot silently change a figure, and they take every
input path as an argument, so an installed package never assumes a directory
exists. Each module also exposes a ``render_*`` function that takes loaded
data or a path plus an output path prefix, so ``render.py`` can call it
directly without a subprocess.

Needs the optional extra: pip install forecast-cruxes-verify[figures]
"""
