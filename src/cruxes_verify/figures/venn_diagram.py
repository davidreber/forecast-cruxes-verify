"""Proportional Venn diagram from set-inclusion JSON data.

CLI:
    python -m cruxes_verify.figures.venn_diagram --results_json PATH --output_path PATH
        [--contrasts_per_side INT] [--questions COMMA_LIST]
"""
import matplotlib
matplotlib.use('Agg')

import argparse
import json
import math
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath


# Wong colorblind palette
_COLOR_INTROSPECTED = '#de8f05'   # orange
_COLOR_EXTRACTED = '#029e73'      # teal
_COLOR_OVERLAP = '#0173b2'        # blue


def _load(data):
    """``data`` is either a path to a set_inclusion_*.json file or a dict
    already loaded from one."""
    if isinstance(data, (str, Path)):
        with open(data) as f:
            return json.load(f)
    return data


def _load_stats(data, contrasts_per_side: int, questions: list | None) -> dict:
    """Load and optionally filter stats from set-inclusion data."""
    results = _load(data)

    per_contrasts_per_side = results['per_contrasts_per_side']
    count_str = str(contrasts_per_side)
    if count_str not in per_contrasts_per_side:
        available = sorted(per_contrasts_per_side.keys(), key=int)
        raise ValueError(
            f"contrasts_per_side={contrasts_per_side} not found in JSON. Available: {available}"
        )

    entry = per_contrasts_per_side[count_str]

    if questions is None:
        summary = entry['summary']
        return {
            'shared_frac_mean': summary['shared_frac_mean'],
            'shared_frac_se': summary['shared_frac_se'],
            'introspected_only_frac_mean': summary['introspected_only_frac_mean'],
            'introspected_only_frac_se': summary['introspected_only_frac_se'],
            'extracted_only_frac_mean': summary['extracted_only_frac_mean'],
            'extracted_only_frac_se': summary['extracted_only_frac_se'],
        }

    # Recompute from per_question for the requested questions
    per_question = entry['per_question']
    missing = [q for q in questions if q not in per_question]
    if missing:
        raise ValueError(f"Questions not found in JSON: {missing}")

    shared = np.array([per_question[q]['shared_frac'] for q in questions])
    introspected_only = np.array([per_question[q]['introspected_only_frac'] for q in questions])
    extracted_only = np.array([per_question[q]['extracted_only_frac'] for q in questions])
    n = len(questions)

    def _mean_se(arr):
        mean = arr.mean()
        se = arr.std(ddof=1) / math.sqrt(n) if n > 1 else 0.0
        return float(mean), float(se)

    sm, ss = _mean_se(shared)
    im, ise = _mean_se(introspected_only)
    em, ese = _mean_se(extracted_only)

    return {
        'shared_frac_mean': sm,
        'shared_frac_se': ss,
        'introspected_only_frac_mean': im,
        'introspected_only_frac_se': ise,
        'extracted_only_frac_mean': em,
        'extracted_only_frac_se': ese,
    }


def _circle_intersection_points(cx1, cy1, r1, cx2, cy2, r2):
    """Return the two intersection points of two circles, or None if they don't intersect."""
    d = math.hypot(cx2 - cx1, cy2 - cy1)
    if d > r1 + r2 or d < abs(r1 - r2) or d == 0:
        return None
    a = (r1**2 - r2**2 + d**2) / (2 * d)
    h = math.sqrt(max(0.0, r1**2 - a**2))
    mx = cx1 + a * (cx2 - cx1) / d
    my = cy1 + a * (cy2 - cy1) / d
    dx = h * (cy2 - cy1) / d
    dy = h * (cx2 - cx1) / d
    return (mx + dx, my - dy), (mx - dx, my + dy)


def _lens_path(cx1, cy1, r1, cx2, cy2, r2, n_points=256):
    """Build a matplotlib Path for the lens-shaped intersection of two circles."""
    pts = _circle_intersection_points(cx1, cy1, r1, cx2, cy2, r2)
    if pts is None:
        return None

    top, bot = pts

    # Angle ranges for the arc on each circle that forms the lens boundary
    # Arc on circle 1 (right-facing arc from bot to top)
    a1_start = math.atan2(bot[1] - cy1, bot[0] - cx1)
    a1_end = math.atan2(top[1] - cy1, top[0] - cx1)
    # Arc on circle 2 (left-facing arc from top to bot)
    a2_start = math.atan2(top[1] - cy2, top[0] - cx2)
    a2_end = math.atan2(bot[1] - cy2, bot[0] - cx2)

    def _arc_points(cx, cy, r, a_start, a_end, going_ccw, n):
        """Sample n points along an arc."""
        if going_ccw:
            if a_end <= a_start:
                a_end += 2 * math.pi
        else:
            if a_end >= a_start:
                a_end -= 2 * math.pi
        angles = np.linspace(a_start, a_end, n)
        return np.column_stack([cx + r * np.cos(angles), cy + r * np.sin(angles)])

    # Circle 1: go counterclockwise from bot to top (right side of lens)
    arc1 = _arc_points(cx1, cy1, r1, a1_start, a1_end, going_ccw=False, n=n_points // 2)
    # Circle 2: go counterclockwise from top to bot (left side of lens)
    arc2 = _arc_points(cx2, cy2, r2, a2_start, a2_end, going_ccw=True, n=n_points // 2)

    verts = np.vstack([arc1, arc2])
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(verts) - 2) + [MplPath.CLOSEPOLY]
    return MplPath(verts, codes)


def _compute_geometry(introspected_only: float, shared: float, extracted_only: float):
    """Compute circle centers/radii in a unit coordinate system.

    Both circles have equal radius (they represent subsets of the same
    number of clusters, so unequal sizes would misleadingly suggest
    different population sizes). The overlap lens area is proportional to
    the shared fraction.

    Returns (cx1, cy1, r1, cx2, cy2, r2) in data units.
    """
    total = introspected_only + shared + extracted_only  # should be ~1.0

    # Equal-sized circles: both sides draw from the same cluster set.
    r1 = 1.0
    r2 = 1.0

    # Target lens area so that lens / union = shared / total.
    # Union = 2*pi*r^2 - lens, so lens / (2*pi - lens) = shared / total,
    # giving lens = 2*pi * shared / (total + shared).
    target_lens = 2 * math.pi * shared / (total + shared) if shared > 0 else 0.0

    def lens_area(d, r_a, r_b):
        if d >= r_a + r_b:
            return 0.0
        if d <= abs(r_a - r_b):
            return math.pi * min(r_a, r_b) ** 2
        cos_a = (d**2 + r_a**2 - r_b**2) / (2 * d * r_a)
        cos_b = (d**2 + r_b**2 - r_a**2) / (2 * d * r_b)
        cos_a = max(-1.0, min(1.0, cos_a))
        cos_b = max(-1.0, min(1.0, cos_b))
        alpha = math.acos(cos_a)
        beta = math.acos(cos_b)
        return r_a**2 * (alpha - math.sin(alpha) * math.cos(alpha)) + r_b**2 * (beta - math.sin(beta) * math.cos(beta))

    # Binary search for center distance d such that lens_area(d) = target_lens
    d_min = abs(r1 - r2)
    d_max = r1 + r2
    for _ in range(100):
        d_mid = (d_min + d_max) / 2
        la = lens_area(d_mid, r1, r2)
        if la > target_lens:
            d_min = d_mid
        else:
            d_max = d_mid
    d = (d_min + d_max) / 2

    cx1 = -d / 2
    cx2 = d / 2
    cy = 0.0

    return cx1, cy, r1, cx2, cy, r2


def render_venn(data, output_path, contrasts_per_side=None, questions=None):
    """Draw the proportional Venn diagram and save it as a PNG.

    ``data`` is either a path to a set_inclusion_*.json file or a dict
    already loaded from one. ``output_path`` is a path prefix, without the
    ``.png`` extension. ``contrasts_per_side`` defaults to the file's
    ``metadata.max_contrasts_per_side``.
    """
    results = _load(data)
    if contrasts_per_side is None:
        contrasts_per_side = results.get('metadata', {}).get('max_contrasts_per_side')
    if contrasts_per_side is None:
        raise ValueError(
            'contrasts_per_side is required when the JSON metadata does not '
            'contain max_contrasts_per_side.'
        )

    stats = _load_stats(results, contrasts_per_side, questions)

    introspected_only = stats['introspected_only_frac_mean']
    shared = stats['shared_frac_mean']
    extracted_only = stats['extracted_only_frac_mean']

    cx1, cy1, r1, cx2, cy2, r2 = _compute_geometry(introspected_only, shared, extracted_only)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.set_aspect('equal')
    ax.axis('off')

    # Very subtle hatch: single-char pattern, 15% opacity white, thin lines.
    # Provides texture for colorblind accessibility without obscuring labels.
    _HATCH_ALPHA = (1.0, 1.0, 1.0, 0.15)

    matplotlib.rcParams['hatch.linewidth'] = 0.4

    left_circle = mpatches.Circle(
        (cx1, cy1), r1,
        facecolor=_COLOR_INTROSPECTED, alpha=0.85,
        hatch='/', edgecolor=_HATCH_ALPHA,
        linewidth=0.5, zorder=2,
    )
    ax.add_patch(left_circle)

    right_circle = mpatches.Circle(
        (cx2, cy2), r2,
        facecolor=_COLOR_EXTRACTED, alpha=0.85,
        hatch='\\', edgecolor=_HATCH_ALPHA,
        linewidth=0.5, zorder=2,
    )
    ax.add_patch(right_circle)

    lens = _lens_path(cx1, cy1, r1, cx2, cy2, r2)
    if lens is not None:
        overlap_patch = PathPatch(
            lens,
            facecolor=_COLOR_OVERLAP, alpha=0.85,
            hatch='+', edgecolor=_HATCH_ALPHA,
            linewidth=0.5, zorder=3,
        )
        ax.add_patch(overlap_patch)

    # --- Text labels (percentages inside regions) ---
    pct_introspected = f"{round(introspected_only * 100):d}%"
    pct_shared = f"{round(shared * 100):d}%"
    pct_extracted = f"{round(extracted_only * 100):d}%"

    label_kw = dict(ha='center', va='center', fontsize=14, fontweight='bold', zorder=5)

    # Left-only region center: slightly left of cx1
    ax.text(cx1 - r1 * 0.38, cy1, pct_introspected, color='white', **label_kw)
    # Overlap center
    ax.text((cx1 + cx2) / 2, (cy1 + cy2) / 2, pct_shared, color='white', **label_kw)
    # Right-only region center: slightly right of cx2
    ax.text(cx2 + r2 * 0.38, cy2, pct_extracted, color='white', **label_kw)

    # --- Name labels above circles ---
    name_kw = dict(ha='center', va='bottom', fontsize=12, zorder=5)
    ax.text(cx1 - r1 * 0.2, cy1 + r1 + 0.07, "Introspected", color=_COLOR_INTROSPECTED, **name_kw)
    ax.text(cx2 + r2 * 0.2, cy2 + r2 + 0.07, "Extracted", color=_COLOR_EXTRACTED, **name_kw)

    # Auto-fit view
    margin = max(r1, r2) * 0.35
    x_lo = cx1 - r1 - margin
    x_hi = cx2 + r2 + margin
    y_lo = min(cy1, cy2) - max(r1, r2) - margin
    y_hi = max(cy1, cy2) + max(r1, r2) + margin * 2.2  # extra room for name labels
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)

    fig.patch.set_facecolor('white')
    fig.tight_layout()

    fig.savefig(f"{output_path}.png", dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    print(f"Saved {output_path}.png")
    print(
        f"  introspected_only={introspected_only:.3f}  shared={shared:.3f}  "
        f"extracted_only={extracted_only:.3f}  "
        f"(SE: ±{stats['introspected_only_frac_se']:.3f} / ±{stats['shared_frac_se']:.3f} "
        f"/ ±{stats['extracted_only_frac_se']:.3f})"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Draw a proportional Venn diagram from set-inclusion JSON data."
    )
    parser.add_argument('--results_json', required=True, help='Path to results JSON file.')
    parser.add_argument('--output_path', required=True, help='Output path prefix (no extension).')
    parser.add_argument('--contrasts_per_side', type=int, default=None,
                        help='Contrasts per side to plot (default: max_contrasts_per_side from metadata).')
    parser.add_argument(
        '--questions', default=None,
        help='Comma-separated list of question ids to filter to before computing stats.',
    )
    args = parser.parse_args()

    questions = [q.strip() for q in args.questions.split(',')] if args.questions else None

    render_venn(args.results_json, args.output_path,
                contrasts_per_side=args.contrasts_per_side, questions=questions)


if __name__ == '__main__':
    main()
