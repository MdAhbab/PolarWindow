"""Figure: Blue Ghost 1's designed phasing-loop cost per launch day, parsed from the day table
that make validate-trip prints, saved first as out/validate_trip.txt:

    make validate-trip > docs/report/scripts/out/validate_trip.txt

Writes docs/report/fig-loops.pdf."""
import re
from pathlib import Path
import matplotlib as mpl
mpl.use("pdf")
import matplotlib.pyplot as plt

mpl.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 9.0, "axes.labelsize": 9.0, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "legend.fontsize": 8.5, "grid.color": "#E5E7EB", "grid.linestyle": "--", "grid.linewidth": 0.5,
    "figure.facecolor": "white", "axes.facecolor": "white", "pdf.fonttype": 42,
    "axes.edgecolor": "#111827", "text.color": "#111827", "axes.labelcolor": "#111827",
})
HERE = Path(__file__).resolve().parent
txt = (HERE / "out" / "validate_trip.txt").read_text()
rows = re.findall(r"^\| ([+-]\d+) \| (\d) \| ([+-]\d+) \| ([\d.]+) \| [^|]+\| [^|]+\| ([\d.]+) \|", txt, re.M)
flown = sum(float(x) for x in re.search(r"burns ([\d.]+) / ([\d.]+) / ([\d.]+) m/s", txt).groups())
day = [int(r[0]) for r in rows]; loops = [int(r[1]) for r in rows]; tot = [float(r[4]) for r in rows]
style = {3: ("#2563EB", ""), 2: ("#E8710A", "///"), 1: ("#059669", "xxx")}
fig, ax = plt.subplots(figsize=(6.3, 2.3))
ax.grid(True, axis="y"); ax.set_axisbelow(True)
for n in (3, 2, 1):
    xs = [d for d, l in zip(day, loops) if l == n]; ys = [t for t, l in zip(tot, loops) if l == n]
    c, h = style[n]
    ax.bar(xs, ys, width=0.7, color=c if not h else "white", edgecolor=c, hatch=h, linewidth=1.0,
           label=f"{n} loop{'s' if n > 1 else ''}")
for d, t in zip(day, tot):
    ax.text(d, t + 3, f"{t:.0f}", ha="center", va="bottom", fontsize=8.5)
ax.axhline(flown, color="#6B7280", lw=1.0, ls="--", label=f"flown burns, {flown:.1f} m/s")
ax.set_xticks(day); ax.set_xticklabels([f"{d:+d}" if d else "0 (flown)" for d in day])
ax.set_xlabel("Launch day relative to the flown launch")
ax.set_ylabel("Designed burns (m/s)")
ax.set_ylim(0, max(tot) * 1.28)
ax.legend(loc="upper right", bbox_to_anchor=(1.0, 1.02), frameon=False, ncol=4)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout(pad=0.3)
fig.savefig(HERE.parent / "fig-loops.pdf",
            metadata={"Creator": "POLAR WINDOW report", "Producer": "POLAR WINDOW report", "Title": "Phasing loop cost per day"})
print(len(rows), "days; flown burns", round(flown, 2), "; cheapest", min(tot), "next", sorted(tot)[1])
