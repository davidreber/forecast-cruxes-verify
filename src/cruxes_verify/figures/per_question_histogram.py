"""Per-question histogram of set-inclusion shared fraction.

Compares March Madness with Metaculus at a fixed contrasts_per_side.

CLI:
    python -m cruxes_verify.figures.per_question_histogram \
        --mm_json PATH --meta_json PATH --output_path PATH
"""

import matplotlib
matplotlib.use('Agg')

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


###############################################################
# Constants
###############################################################

# Wong colorblind palette (consistent with polished_set_inclusion.py)
COLOR_OBSERVED = '#0173b2'   # blue
COLOR_BASELINE = '#de8f05'   # orange

HATCH_OBSERVED = '//'



###############################################################
# Data loading
###############################################################

def load_per_question_fracs(data, contrasts_per_side: str = '25'):
    """Load per-question shared_frac and permutation baselines at one count.

    ``data`` is either a path to a set_inclusion_*.json file or a dict
    already loaded from one.

    Returns:
        fracs: 1-D array of observed shared fractions.
        baselines: 1-D array of per-question permutation baselines.
        agg_baseline: aggregate permutation shared mean.
    """
    if isinstance(data, (str, Path)):
        with open(data) as f:
            data = json.load(f)

    entry = data['per_contrasts_per_side'][contrasts_per_side]
    per_question = entry['per_question']

    fracs = []
    baselines = []
    for _question_id, record in per_question.items():
        fracs.append(record['shared_frac'])
        baselines.append(record['permutation']['permutation_shared_mean'])

    agg_baseline = entry['permutation']['permutation_shared_mean']
    return np.array(fracs), np.array(baselines), agg_baseline


###############################################################
# Plotting
###############################################################

def render_per_question_histogram(mm_data, meta_data, output_path, contrasts_per_side=25):
    """Draw side-by-side histograms of per-question shared fraction and save a PNG.

    ``mm_data`` and ``meta_data`` are each either a path to a
    set_inclusion_*.json file or a dict already loaded from one, for March
    Madness and Metaculus respectively. ``output_path`` is a path prefix,
    without the ``.png`` extension.
    """
    count = str(contrasts_per_side)
    mm_fracs, mm_baselines, mm_agg = load_per_question_fracs(mm_data, count)
    meta_fracs, meta_baselines, meta_agg = load_per_question_fracs(meta_data, count)

    fig, (ax_mm, ax_meta) = plt.subplots(
        1, 2, figsize=(10, 4.2), sharey=False
    )

    # --- Bin setup ---
    # Shared x-axis range [0, 1] with consistent bins.
    bins = np.arange(0, 0.75, 0.05)

    # --- MM panel ---
    ax_mm.hist(
        mm_fracs, bins=bins, color=COLOR_OBSERVED, edgecolor='black',
        linewidth=0.6, alpha=0.85, hatch=HATCH_OBSERVED, label='Observed'
    )
    ax_mm.axvline(
        mm_agg, color=COLOR_BASELINE, linewidth=2.0,
        linestyle='--', label=f'Permutation baseline ({mm_agg:.0%})'
    )
    # Per-question baseline range as a shaded band
    ax_mm.axvspan(
        mm_baselines.min(), mm_baselines.max(),
        color=COLOR_BASELINE, alpha=0.10, linewidth=0
    )

    n_below_mm = int(np.sum(mm_fracs < mm_baselines))
    ax_mm.set_title(f'March Madness ({len(mm_fracs)} questions)', fontsize=13)
    ax_mm.set_xlabel(f'Shared fraction at contrasts_per_side = {contrasts_per_side}', fontsize=12)
    ax_mm.set_ylabel('Number of questions', fontsize=12)
    ax_mm.tick_params(axis='both', labelsize=11)
    ax_mm.legend(fontsize=9, loc='upper right', framealpha=0.85)

    # Annotation: N/N below baseline
    ax_mm.text(
        0.97, 0.75,
        f'{n_below_mm}/{len(mm_fracs)} below\nown baseline',
        transform=ax_mm.transAxes, fontsize=10,
        ha='right', va='top',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                  edgecolor='gray', alpha=0.85)
    )

    # --- Meta panel ---
    bins_meta = np.arange(0, 0.80, 0.05)
    ax_meta.hist(
        meta_fracs, bins=bins_meta, color=COLOR_OBSERVED, edgecolor='black',
        linewidth=0.6, alpha=0.85, hatch=HATCH_OBSERVED, label='Observed'
    )
    ax_meta.axvline(
        meta_agg, color=COLOR_BASELINE, linewidth=2.0,
        linestyle='--', label=f'Permutation baseline ({meta_agg:.0%})'
    )
    ax_meta.axvspan(
        meta_baselines.min(), meta_baselines.max(),
        color=COLOR_BASELINE, alpha=0.10, linewidth=0
    )

    n_below_meta = int(np.sum(meta_fracs < meta_baselines))
    n_tied_meta = int(np.sum(meta_fracs == meta_baselines))
    ax_meta.set_title(f'Metaculus ({len(meta_fracs)} questions)', fontsize=13)
    ax_meta.set_xlabel(f'Shared fraction at contrasts_per_side = {contrasts_per_side}', fontsize=12)
    ax_meta.tick_params(axis='both', labelsize=11)
    ax_meta.legend(fontsize=9, loc='upper right', framealpha=0.85)

    # Annotation
    ax_meta.text(
        0.97, 0.75,
        f'{n_below_meta}/{len(meta_fracs)} below\nown baseline',
        transform=ax_meta.transAxes, fontsize=10,
        ha='right', va='top',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                  edgecolor='gray', alpha=0.85)
    )

    fig.tight_layout()

    fig.savefig(f'{output_path}.png', dpi=300, bbox_inches='tight')

    plt.close(fig)
    print(f'Saved {output_path}.png')

    # Print summary statistics for verification
    print('\n--- March Madness ---')
    print(f'  n={len(mm_fracs)}, mean={mm_fracs.mean():.3f}, '
          f'median={np.median(mm_fracs):.3f}, '
          f'min={mm_fracs.min():.3f}, max={mm_fracs.max():.3f}')
    print(f'  zeros={int(np.sum(mm_fracs == 0))}, '
          f'below own baseline={n_below_mm}/{len(mm_fracs)}')
    print(f'  aggregate baseline={mm_agg:.3f}')

    print('\n--- Metaculus ---')
    print(f'  n={len(meta_fracs)}, mean={meta_fracs.mean():.3f}, '
          f'median={np.median(meta_fracs):.3f}, '
          f'min={meta_fracs.min():.3f}, max={meta_fracs.max():.3f}')
    print(f'  zeros={int(np.sum(meta_fracs == 0))}, '
          f'below own baseline={n_below_meta}/{len(meta_fracs)}, '
          f'tied={n_tied_meta}')
    print(f'  aggregate baseline={meta_agg:.3f}')


###############################################################
# CLI
###############################################################

def main():
    parser = argparse.ArgumentParser(
        description='Per-question histogram of shared fractions at a fixed contrasts_per_side.'
    )
    parser.add_argument(
        '--mm_json', required=True,
        help='Path to March Madness set-inclusion JSON.'
    )
    parser.add_argument(
        '--meta_json', required=True,
        help='Path to Metaculus set-inclusion JSON.'
    )
    parser.add_argument(
        '--output_path', required=True,
        help='Output path prefix (without extension).'
    )
    parser.add_argument(
        '--contrasts_per_side', type=int, default=25,
        help='Contrasts per side to read the histogram at (default 25).'
    )
    args = parser.parse_args()

    render_per_question_histogram(args.mm_json, args.meta_json, args.output_path,
                                   contrasts_per_side=args.contrasts_per_side)


if __name__ == '__main__':
    main()
