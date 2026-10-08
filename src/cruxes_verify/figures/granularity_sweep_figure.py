"""Broad-category overlap figure (reviewer rebuttal, request 1).

Plots the observed between-pools shared fraction against the permutation
null across cluster resolutions, coarse to fine. If the observed curve rises
toward the null as clusters coarsen, the fine-grained premise mismatch is a
granularity artifact; a gap that persists at coarse resolution is a genuine
category difference. Input is a granularity_sweep_*.json file, as produced by
the package's report step run with ``--baselines``.
"""

import matplotlib
matplotlib.use('Agg')

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


###############################################################
# Constants (Wong colorblind palette, consistent with paper figures)
###############################################################

COLOR_OBSERVED = '#0173b2'   # blue
COLOR_BASELINE = '#de8f05'   # orange



###############################################################
# Data loading
###############################################################

def load_per_resolution(data):
    """Load aggregate per-resolution observed and permutation-null curves.

    ``data`` is either a path to a granularity_sweep_*.json file or a dict
    already loaded from one.
    """
    if isinstance(data, (str, Path)):
        with open(data) as f:
            data = json.load(f)
    rows = data['per_resolution']
    resolution = np.array([r['resolution'] for r in rows])
    obs = np.array([r['shared_frac_mean'] for r in rows])
    obs_se = np.array([r['shared_frac_se'] or 0.0 for r in rows])
    perm = np.array([r['permutation_shared_mean'] for r in rows])
    perm_se = np.array([r['permutation_shared_se'] or 0.0 for r in rows])
    return resolution, obs, obs_se, perm, perm_se, data['metadata']


###############################################################
# Plotting
###############################################################

def render_granularity_sweep(data, output_path):
    """Draw the figure and save it as a PNG.

    ``data`` is either a path to a granularity_sweep_*.json file or a dict
    already loaded from one. ``output_path`` is a path prefix, without the
    ``.png`` extension.
    """
    resolution, obs, obs_se, perm, perm_se, meta = load_per_resolution(data)

    fig, ax = plt.subplots(figsize=(7, 4.6))

    # Observed between-pools overlap: solid line, circle markers.
    ax.plot(resolution, obs, color=COLOR_OBSERVED, linewidth=2.2, marker='o',
            markersize=6, label='Observed (introspected vs extracted)')
    ax.fill_between(resolution, obs - obs_se, obs + obs_se,
                    color=COLOR_OBSERVED, alpha=0.18, linewidth=0)

    # Permutation null: dashed line, square markers.
    ax.plot(resolution, perm, color=COLOR_BASELINE, linewidth=2.2, marker='s',
            markersize=6, linestyle='--', label='Permutation null')
    ax.fill_between(resolution, perm - perm_se, perm + perm_se,
                    color=COLOR_BASELINE, alpha=0.18, linewidth=0)

    ax.set_xlabel('Cluster resolution (clusters / items)'
                  '\n(broad categories  $\\leftarrow$      $\\rightarrow$  fine-grained)',
                  fontsize=12)
    ax.set_ylabel('Shared fraction', fontsize=12)
    ax.set_ylim(-0.02, 1.02)
    ax.tick_params(axis='both', labelsize=11)
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.legend(fontsize=10, loc='upper right', framealpha=0.9)

    fig.tight_layout()
    fig.savefig(f'{output_path}.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved {output_path}.png')

    # Verification summary
    gap = obs - perm
    print(f"\n--- Granularity sweep ({meta.get('label')}, "
          f"{meta.get('n_questions')} questions) ---")
    for i in range(len(resolution)):
        print(f"  resolution={resolution[i]:.1f}: observed={obs[i]:.3f} "
              f"null={perm[i]:.3f} gap={gap[i]:+.3f}")


###############################################################
# CLI
###############################################################

def main():
    parser = argparse.ArgumentParser(
        description='Broad-category overlap: granularity sweep figure.'
    )
    parser.add_argument('--input_json', required=True,
                        help='granularity_sweep_*.json from the report step.')
    parser.add_argument('--output_path', required=True,
                        help='Output path prefix (without extension).')
    args = parser.parse_args()
    render_granularity_sweep(args.input_json, args.output_path)


if __name__ == '__main__':
    main()
