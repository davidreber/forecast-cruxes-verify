"""Stacked area chart of set-inclusion fractions across contrasts_per_side.

CLI:
    python -m cruxes_verify.figures.polished_set_inclusion \
        --results_json PATH --output_path PATH
"""

import matplotlib
matplotlib.use('Agg')

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


###############################################################
# Constants
###############################################################

# Wong colorblind palette (consistent with venn_diagram.py)
COLOR_INTROSPECTED_ONLY = '#de8f05'   # orange
COLOR_SHARED = '#0173b2'              # blue
COLOR_EXTRACTED_ONLY = '#029e73'      # teal

HATCH_INTROSPECTED_ONLY = '/'
HATCH_SHARED = '+'
HATCH_EXTRACTED_ONLY = '\\'


def _load(data):
    """``data`` is either a path to a set_inclusion_*.json file or a dict
    already loaded from one."""
    if isinstance(data, (str, Path)):
        with open(data) as f:
            return json.load(f)
    return data


def compute_stats(per_contrasts_per_side, question_filter=None):
    """Return arrays (counts, extracted_mean, extracted_se, shared_mean,
    shared_se, introspected_mean, introspected_se).

    With no filter, the aggregate summary at each count is used directly.
    With a filter, the fractions are recomputed from the per-question
    records for only those question ids.
    """
    counts = sorted(int(c) for c in per_contrasts_per_side)
    extracted_means, extracted_ses = [], []
    shared_means, shared_ses = [], []
    introspected_means, introspected_ses = [], []

    for count in counts:
        entry = per_contrasts_per_side[str(count)]

        if question_filter is None:
            summary = entry['summary']
            extracted_means.append(summary['extracted_only_frac_mean'])
            extracted_ses.append(summary['extracted_only_frac_se'])
            shared_means.append(summary['shared_frac_mean'])
            shared_ses.append(summary['shared_frac_se'])
            introspected_means.append(summary['introspected_only_frac_mean'])
            introspected_ses.append(summary['introspected_only_frac_se'])
        else:
            per_question = entry['per_question']
            vals_extracted, vals_shared, vals_introspected = [], [], []
            for question_id in question_filter:
                if question_id in per_question:
                    record = per_question[question_id]
                    vals_extracted.append(record['extracted_only_frac'])
                    vals_shared.append(record['shared_frac'])
                    vals_introspected.append(record['introspected_only_frac'])
            n = len(vals_extracted)
            if n == 0:
                extracted_means.append(0.0); extracted_ses.append(0.0)
                shared_means.append(0.0); shared_ses.append(0.0)
                introspected_means.append(0.0); introspected_ses.append(0.0)
            else:
                arr_extracted = np.array(vals_extracted)
                arr_shared = np.array(vals_shared)
                arr_introspected = np.array(vals_introspected)
                extracted_means.append(arr_extracted.mean())
                extracted_ses.append(arr_extracted.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0)
                shared_means.append(arr_shared.mean())
                shared_ses.append(arr_shared.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0)
                introspected_means.append(arr_introspected.mean())
                introspected_ses.append(arr_introspected.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0)

    return (
        np.array(counts),
        np.array(extracted_means), np.array(extracted_ses),
        np.array(shared_means), np.array(shared_ses),
        np.array(introspected_means), np.array(introspected_ses),
    )


def render_set_inclusion(data, output_path, title='', question_filter=None):
    """Draw the stacked area chart and save it as a PNG.

    ``data`` is either a path to a set_inclusion_*.json file or a dict
    already loaded from one. ``output_path`` is a path prefix, without the
    ``.png`` extension. ``question_filter``, if given, is a list of question
    ids to restrict the chart to.
    """
    results = _load(data)
    per_contrasts_per_side = results['per_contrasts_per_side']
    counts, extracted_mean, extracted_se, shared_mean, shared_se, introspected_mean, introspected_se = (
        compute_stats(per_contrasts_per_side, question_filter)
    )

    # Band boundaries
    boundary_es = extracted_mean                # bottom of shared
    boundary_si = extracted_mean + shared_mean   # bottom of introspected only (= top of shared)

    fig, ax = plt.subplots(figsize=(8, 5))

    _HATCH_EDGE = (1.0, 1.0, 1.0, 0.15)
    matplotlib.rcParams['hatch.linewidth'] = 0.4

    # --- Stacked bands ---
    # Bottom band: extracted only (0 -> extracted_mean)
    ax.fill_between(counts, 0, extracted_mean,
                    color=COLOR_EXTRACTED_ONLY, hatch=HATCH_EXTRACTED_ONLY,
                    edgecolor=_HATCH_EDGE, linewidth=0.5, alpha=0.85,
                    label='Extracted only')

    # Middle band: shared (extracted_mean -> extracted_mean+shared_mean)
    ax.fill_between(counts, boundary_es, boundary_si,
                    color=COLOR_SHARED, hatch=HATCH_SHARED,
                    edgecolor=_HATCH_EDGE, linewidth=0.5, alpha=0.85,
                    label='Shared')

    # Top band: introspected only (extracted_mean+shared_mean -> 1.0)
    ax.fill_between(counts, boundary_si, 1.0,
                    color=COLOR_INTROSPECTED_ONLY, hatch=HATCH_INTROSPECTED_ONLY,
                    edgecolor=_HATCH_EDGE, linewidth=0.5, alpha=0.85,
                    label='Introspected only')

    # --- Uncertainty ribbons on boundaries ---
    # Lower boundary (extracted only / shared): SE from extracted only
    ax.fill_between(counts,
                    boundary_es - extracted_se,
                    boundary_es + extracted_se,
                    color='white', alpha=0.25, linewidth=0)

    # Upper boundary (shared / introspected only): propagated SE
    upper_se = np.sqrt(extracted_se**2 + shared_se**2)
    ax.fill_between(counts,
                    boundary_si - upper_se,
                    boundary_si + upper_se,
                    color='white', alpha=0.25, linewidth=0)

    # --- Percentage annotations at the largest count ---
    count_last = counts[-1]
    x_offset = count_last * 0.03

    extracted_pct = extracted_mean[-1]
    shared_pct = shared_mean[-1]
    introspected_pct = introspected_mean[-1]

    # Vertical centers of each band at the largest count
    center_extracted = extracted_pct / 2
    center_shared = extracted_pct + shared_pct / 2
    center_introspected = (extracted_pct + shared_pct) + introspected_pct / 2

    for center, pct in [(center_extracted, extracted_pct), (center_shared, shared_pct),
                        (center_introspected, introspected_pct)]:
        ax.text(count_last + x_offset, center, f'{pct:.0%}',
                fontsize=11, va='center', ha='left', color='black')

    # --- Axes formatting ---
    ax.set_xlim(counts[0], counts[-1] + (counts[-1] - counts[0]) * 0.08)
    ax.set_ylim(0, 1)
    ax.set_xlabel('Premises per side (contrasts_per_side)', fontsize=15)
    ax.set_ylabel('Fraction of clusters', fontsize=15)
    ax.tick_params(axis='both', labelsize=13)

    if title:
        ax.set_title(title, fontsize=14)

    # --- Legend with color+hatch swatches ---
    legend_patches = [
        mpatches.Patch(facecolor=COLOR_INTROSPECTED_ONLY, hatch=HATCH_INTROSPECTED_ONLY,
                       edgecolor=_HATCH_EDGE, linewidth=0.5, label='Introspected only'),
        mpatches.Patch(facecolor=COLOR_SHARED, hatch=HATCH_SHARED,
                       edgecolor=_HATCH_EDGE, linewidth=0.5, label='Shared'),
        mpatches.Patch(facecolor=COLOR_EXTRACTED_ONLY, hatch=HATCH_EXTRACTED_ONLY,
                       edgecolor=_HATCH_EDGE, linewidth=0.5, label='Extracted only'),
    ]
    ax.legend(handles=legend_patches, loc='upper right', fontsize=10,
              framealpha=0.85)

    fig.tight_layout()

    fig.savefig(f'{output_path}.png', dpi=300, bbox_inches='tight')

    plt.close(fig)
    print(f'Saved {output_path}.png')


###############################################################
# CLI
###############################################################

def main():
    parser = argparse.ArgumentParser(
        description='Stacked area chart of set-inclusion fractions across contrasts_per_side.'
    )
    parser.add_argument('--results_json', required=True,
                        help='Path to set-inclusion JSON results file.')
    parser.add_argument('--output_path', required=True,
                        help='Output path prefix (without extension).')
    parser.add_argument('--title', default='',
                        help='Optional chart title.')
    parser.add_argument('--questions', default=None,
                        help='Comma-separated list of question ids to filter to.')
    args = parser.parse_args()

    question_filter = None
    if args.questions:
        question_filter = [q.strip() for q in args.questions.split(',') if q.strip()]

    render_set_inclusion(args.results_json, args.output_path, title=args.title,
                          question_filter=question_filter)


if __name__ == '__main__':
    main()
