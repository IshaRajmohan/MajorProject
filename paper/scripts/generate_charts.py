"""
Generates the paper's data-driven figures directly from the numbers verified
in paper/evidence/*.txt (demo_person_c_output.txt, eval_comparison_report.txt,
sensitivity_sweep_report.txt). No numbers here are invented — every value is
transcribed from those saved execution logs; see NyayaOS_CAMS_Audit.md.

Run:  python3 scripts/generate_charts.py
Output: ../figures_pdf/fig4_confidence_trajectory.pdf
        ../figures_pdf/fig5_match_rate.pdf
        ../figures_pdf/fig6_sensitivity_range.pdf
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "figures_pdf"
OUT.mkdir(exist_ok=True)

# ---- palette (validated categorical + status slots; print/grayscale-safe) ----
BLUE = "#2a78d6"       # CAMS / primary series
BLUE_DARK = "#184f95"
ORANGE = "#eb6834"     # baselines
GOOD = "#0ca30c"       # updated
WARNING = "#c98500"    # retained
CRITICAL = "#d03b3b"   # unresolved / lost candidate
GRID = "#d8d8d4"
TEXT = "#26261f"
MUTED = "#6b6a63"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9.5,
    "text.color": TEXT,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "axes.linewidth": 0.8,
    "pdf.fonttype": 42,
})


def style_axes(ax, y_grid=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    if y_grid:
        ax.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)


# ======================================================================
# Fig 4 — Confidence trajectory across the bail_status observation sequence
# (Section 7.2 numbers, demo_person_c_output.txt)
# ======================================================================
fig, ax = plt.subplots(figsize=(6.6, 3.0), dpi=300)

steps = [1, 2, 3, 4, 5, 6]
step_labels = [
    "1\ncourt\ngranted",
    "2\n+police\ngranted",
    "3\n+lawyer\ngranted",
    "4\n+police\ndenied",
    "5\n+police\nin_custody",
    "6\n+court\ndup. granted",
]
twin_confidence = [0.635, 0.8517, 0.9183, 0.9183, 0.9183, 0.9183]
decisions = ["updated", "updated", "updated", "updated", "updated", "retained"]

# synchronized Twin State confidence line
line_colors = [GOOD if d == "updated" else WARNING for d in decisions]
ax.plot(steps, twin_confidence, color=BLUE, linewidth=2, zorder=3, solid_capstyle="round")
for x, y, d in zip(steps, twin_confidence, decisions):
    marker = "o" if d == "updated" else "D"
    face = GOOD if d == "updated" else "white"
    edge = GOOD if d == "updated" else WARNING
    ax.scatter([x], [y], s=60 if d == "updated" else 70, marker=marker,
               facecolor=face, edgecolor=edge, linewidth=1.6, zorder=4)

# losing / competing candidates introduced at steps 4, 5, 6
losers = {4: 0.665, 5: 0.415}
for x, y in losers.items():
    ax.scatter([x], [y], s=55, marker="x", color=CRITICAL, linewidth=1.8, zorder=4)

# annotate the duplicate tie at step 6
ax.annotate("tie: C=0.918 vs 0.918\nmargin=0 < δ, so retained",
            xy=(6, 0.9183), xytext=(4.35, 0.975),
            fontsize=7.6, color=WARNING,
            arrowprops=dict(arrowstyle="-", color=WARNING, lw=0.8))
ax.annotate("conflicting\n(denied)", xy=(4, 0.665), xytext=(3.35, 0.50),
            fontsize=7.6, color=CRITICAL,
            arrowprops=dict(arrowstyle="-", color=CRITICAL, lw=0.8))
ax.annotate("delayed 25d\n(in_custody)", xy=(5, 0.415), xytext=(5.05, 0.26),
            fontsize=7.6, color=CRITICAL,
            arrowprops=dict(arrowstyle="-", color=CRITICAL, lw=0.8))

ax.axhline(0.6, color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2)
ax.text(0.92, 0.615, r"$\tau=0.6$", fontsize=8, color=MUTED, ha="left")

ax.set_xticks(steps)
ax.set_xticklabels(step_labels, fontsize=7.6)
ax.set_ylim(0, 1.05)
ax.set_ylabel("CAMS confidence  $C$")
ax.set_xlabel("Observation ingested for the bail\\_status fact (in order)", labelpad=8)
style_axes(ax)

legend_handles = [
    plt.Line2D([0], [0], marker="o", color=BLUE, markerfacecolor=GOOD, markeredgecolor=GOOD,
               linestyle="-", linewidth=2, label="Twin State confidence (updated)"),
    plt.Line2D([0], [0], marker="D", color="none", markerfacecolor="white", markeredgecolor=WARNING,
               linestyle="none", label="Twin State unchanged (retained)"),
    plt.Line2D([0], [0], marker="x", color=CRITICAL, linestyle="none", markeredgewidth=1.8,
               label="Losing competing candidate"),
]
ax.legend(handles=legend_handles, loc="lower right", fontsize=7.3, frameon=False)

fig.tight_layout()
fig.savefig(OUT / "fig4_confidence_trajectory.pdf")
plt.close(fig)

# ======================================================================
# Fig 5 — Value-match rate by method (Table III aggregate),
# eval_comparison_report.txt
# ======================================================================
fig, ax = plt.subplots(figsize=(6.6, 3.0), dpi=300)

# Order is written top-to-bottom as it should read on the chart; invert_yaxis()
# below flips the axis rather than reversing the data, which is what caused a
# label/bar mismatch in an earlier draft of this script.
methods = [
    "CAMS (full)", "CAMS − A", "CAMS − T", "CAMS − X", "CAMS − E",
    "Fixed authority", "Latest-ingestion–wins", "Majority voting",
]
rates = [80, 80, 60, 60, 60, 100, 40, 80]
is_cams = [True, True, True, True, True, False, False, False]
colors = [BLUE if c else ORANGE for c in is_cams]
hatches = [None if c else "///" for c in is_cams]

y_pos = list(range(len(methods)))
bars = ax.barh(y_pos, rates, color=colors, height=0.6, zorder=3,
                edgecolor="white", linewidth=0.6)
for bar, h in zip(bars, hatches):
    if h:
        bar.set_hatch(h)
        bar.set_edgecolor(BLUE_DARK)

ax.set_yticks(y_pos)
ax.set_yticklabels(methods, fontsize=8.6)
ax.invert_yaxis()  # first method (CAMS full) at the top
ax.set_xlim(0, 108)
ax.set_xlabel("Value-match rate across 5 controlled scenarios (%)")
ax.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0)
ax.set_axisbelow(True)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)
ax.spines["bottom"].set_color(MUTED)
ax.tick_params(left=False)

for bar, rate in zip(bars, rates):
    ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2, f"{rate}%",
            va="center", fontsize=8, color=TEXT)

# asterisk annotation on fixed-authority bar
fixed_idx = methods.index("Fixed authority")
ax.text(rates[fixed_idx] + 10.5, fixed_idx, "*", fontsize=11, color=MUTED, va="center")

legend_handles = [
    plt.Rectangle((0, 0), 1, 1, facecolor=BLUE, edgecolor="white", label="CAMS (full model / ablation)"),
    plt.Rectangle((0, 0), 1, 1, facecolor=ORANGE, hatch="///", edgecolor=BLUE_DARK, label="Baseline"),
]
ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.22),
          ncol=2, fontsize=7.8, frameon=False)

fig.tight_layout()
fig.subplots_adjust(bottom=0.28)
fig.savefig(OUT / "fig5_match_rate.pdf")
plt.close(fig)

# ======================================================================
# Fig 6 — Threshold (tau) decision-boundary range per scenario,
# sensitivity_sweep_report.txt
# ======================================================================
fig, ax = plt.subplots(figsize=(6.6, 2.6), dpi=300)

scenarios = ["Conflicting", "Delayed", "Noisy", "Corroboration", "Duplicate"]
tau_boundary = [0.85, 0.80, 0.70, 0.75, 0.30]  # 0.30 = lower sweep bound; never updates
tau_default = 0.6
never_updates = [False, False, False, False, True]

y_pos = range(len(scenarios))
for i, (y, boundary, never) in enumerate(zip(y_pos, tau_boundary, never_updates)):
    y = len(scenarios) - 1 - y
    if never:
        ax.plot([0.30, 0.30], [y, y], marker="x", color=CRITICAL, markersize=8, linewidth=0, zorder=3)
        ax.text(0.315, y, "never updates in swept range", fontsize=7.6, color=CRITICAL, va="center")
    else:
        ax.plot([0.30, boundary], [y, y], color=BLUE, linewidth=4, solid_capstyle="round",
                 zorder=3, alpha=0.85)
        ax.scatter([boundary], [y], s=40, color=BLUE_DARK, zorder=4)
        ax.text(boundary + 0.015, y, f"boundary τ={boundary:.2f}", fontsize=7.6, color=BLUE_DARK, va="center")

ax.axvline(tau_default, color=MUTED, linewidth=1.1, linestyle=(0, (4, 3)), zorder=2)
ax.text(tau_default, len(scenarios) - 0.15, r"default $\tau=0.6$", fontsize=8, color=MUTED,
        ha="center", va="bottom")

ax.set_yticks(list(range(len(scenarios))))
ax.set_yticklabels(scenarios[::-1], fontsize=9)
ax.set_xlim(0.28, 1.0)
ax.set_xlabel(r"Range of $\tau$ (with $\delta$=0.1 fixed) for which the scenario resolves to 'updated'")
style_axes(ax)
ax.spines["left"].set_visible(False)
ax.tick_params(left=False)

fig.tight_layout()
fig.savefig(OUT / "fig6_sensitivity_range.pdf")
plt.close(fig)

print("Wrote:")
for f in ["fig4_confidence_trajectory.pdf", "fig5_match_rate.pdf", "fig6_sensitivity_range.pdf"]:
    print(" -", OUT / f)
