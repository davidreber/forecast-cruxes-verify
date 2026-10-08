"""Reviewer simulation for the forecast-cruxes paper.

Given only the paper's data release (inputs), rerun everything downstream of
the recorded language model outputs with the public ``forecast-cruxes``
package (the function), on one's own hardware, and check what comes out
against the paper's numbers (results), which ship with this package in
``expected/``, within tolerances derived from measured two-sample drift.
"""

__version__ = "0.1.0"
