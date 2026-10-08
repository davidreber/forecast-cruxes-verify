"""Within-pool permutation baseline figure (reviewer rebuttal, request 2).

Plots the between-pools observed overlap against the within-introspected and
within-extracted sampling ceilings as a function of contrasts per side.
Within-pool overlap sitting well above the between-pools observed overlap
means the between-pools mismatch is a real distributional difference rather
than sampling noise; a gap between the two within-pool curves exposes
asymmetry in how internally homogeneous each pool is. Input is a
within_pool_split_*.json file, as produced by the package's report step run
with ``--baselines``.
"""

import matplotlib
matplotlib.use('Agg')

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


###############################################################
# Constants (Wong colorblind palette)
###############################################################

COLOR_BETWEEN = '#0173b2'       # blue   -- between pools observed
COLOR_INTROSPECTED = '#029e73'  # green  -- within introspected
COLOR_EXTRACTED = '#de8f05'     # orange -- within extracted
COLOR_PERM = '#949494'          # gray   -- between pools permutation null



###############################################################
# Data loading
###############################################################

def load_per_contrasts_per_side(data):
    """Load the per contrasts-per-side rows.

    ``data`` is either a path to a within_pool_split_*.json file or a dict
    already loaded from one.
    """
    if isinstance(data, (str, Path)):
        with open(data) as f:
            data = json.load(f)
    rows = data['per_contrasts_per_side']
    counts = np.array([r['contrasts_per_side'] for r in rows])

    def col(name):
        return np.array([np.nan if r[name] is None else r[name] for r in rows])

    return {
        'counts': counts,
        'between': col('between_pools_observed_mean'),
        'between_se': col('between_pools_observed_se'),
        'introspected': col('within_introspected_mean'),
        'introspected_se': col('within_introspected_se'),
        'extracted': col('within_extracted_mean'),
        'extracted_se': col('within_extracted_se'),
        'perm': col('between_pools_permutation_mean'),
        'meta': data['metadata'],
    }


###############################################################
# Plotting
###############################################################

def _plot_curve(ax, counts, mean, se, color, marker, linestyle, label):
    ax.plot(counts, mean, color=color, linewidth=2.2, marker=marker, markersize=6,
            linestyle=linestyle, label=label)
    if se is not None:
        ax.fill_between(counts, mean - se, mean + se, color=color, alpha=0.16,
                        linewidth=0)


def render_within_pool_split(data, output_path):
    """Draw the figure and save it as a PNG.

    ``data`` is either a path to a within_pool_split_*.json file or a dict
    already loaded from one. ``output_path`` is a path prefix, without the
    ``.png`` extension.
    """
    d = load_per_contrasts_per_side(data)
    counts = d['counts']

    fig, ax = plt.subplots(figsize=(7, 4.6))

    _plot_curve(ax, counts, d['introspected'], d['introspected_se'], COLOR_INTROSPECTED, 's', '--',
                'Within introspected (two halves)')
    _plot_curve(ax, counts, d['extracted'], d['extracted_se'], COLOR_EXTRACTED, '^', '-.',
                'Within extracted (two halves)')
    _plot_curve(ax, counts, d['between'], d['between_se'], COLOR_BETWEEN, 'o', '-',
                'Between pools observed (introspected vs extracted)')

    if not np.all(np.isnan(d['perm'])):
        ax.plot(counts, d['perm'], color=COLOR_PERM, linewidth=1.6, marker='x',
                markersize=5, linestyle=':', label='Between pools permutation null')

    ax.set_xlabel('Premises per side (contrasts_per_side)', fontsize=12)
    ax.set_ylabel('Shared fraction', fontsize=12)
    ax.set_ylim(-0.02, 1.02)
    ax.tick_params(axis='both', labelsize=11)
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.legend(fontsize=9.5, loc='best', framealpha=0.9)

    fig.tight_layout()
    fig.savefig(f'{output_path}.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved {output_path}.png')

    # Verification summary
    print(f"\n--- Within pool split ({d['meta'].get('label')}, "
          f"{d['meta'].get('n_questions')} questions) ---")
    for i in range(len(counts)):
        print(f"  contrasts_per_side={int(counts[i]):>2}: "
              f"within_introspected={d['introspected'][i]:.3f} "
              f"within_extracted={d['extracted'][i]:.3f} "
              f"between_pools={d['between'][i]:.3f}")


###############################################################
# CLI
###############################################################

def main():
    parser = argparse.ArgumentParser(
        description='Within-pool permutation baselines figure.'
    )
    parser.add_argument('--input_json', required=True,
                        help='within_pool_split_*.json from the report step.')
    parser.add_argument('--output_path', required=True,
                        help='Output path prefix (without extension).')
    args = parser.parse_args()
    render_within_pool_split(args.input_json, args.output_path)


if __name__ == '__main__':
    main()
