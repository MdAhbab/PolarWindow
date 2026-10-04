"""Figure: the Sun's centre and the skyline under it at Connecting Ridge, from export_data.py's
tracks_connecting_ridge.csv. Writes docs/report/fig-sun-skyline.pdf at the report's text width."""
import csv
from pathlib import Path
import matplotlib as mpl
mpl.use("pdf")
import matplotlib.pyplot as plt
import numpy as np

mpl.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 9.0, "axes.titlesize": 9.5, "axes.labelsize": 9.0, "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5, "legend.fontsize": 8.5, "lines.linewidth": 1.5, "grid.color": "#E5E7EB",
    "grid.linestyle": "--", "grid.linewidth": 0.5, "figure.facecolor": "white",
    "axes.facecolor": "white", "pdf.fonttype": 42, "axes.edgecolor": "#111827",
    "text.color": "#111827", "axes.labelcolor": "#111827", "xtick.color": "#111827", "ytick.color": "#111827",
})
HERE = Path(__file__).resolve().parent
src = HERE / "data" / "tracks_connecting_ridge.csv"
out = HERE.parent / "fig-sun-skyline.pdf"
rows = list(csv.DictReader(open(src)))
t = np.array([float(r["t_h"]) for r in rows])
sun = np.array([float(r["sun_el_deg"]) for r in rows])
sky = np.array([float(r["sun_skyline_deg"]) for r in rows])
fig, ax = plt.subplots(figsize=(6.3, 2.5))
ax.grid(True, axis="y")
ax.fill_between(t, sky, sun, where=sun > sky, color="#E8710A", alpha=0.22, linewidth=0,
                label="Sun above the skyline")
ax.plot(t, sun, color="#E8710A", label="Sun centre elevation")
ax.plot(t, sky, color="#2563EB", lw=1.2, ls=(0, (4, 2)), label="Skyline at the Sun's azimuth")
ax.axhline(0, color="#6B7280", lw=0.8, ls=":")
ax.text(8, 0.08, "level (0°)", fontsize=8.5, color="#6B7280", va="bottom")
ax.set_ylim(-4.75, 0.6)
ax.set_xlim(t[0], t[-1])
ax.set_xlabel("Hours from 2027-03-14 00:00 UTC")
ax.set_ylabel("Elevation (°)")
ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), frameon=False, ncol=3, handlelength=2.2,
          columnspacing=1.2, borderaxespad=0.2)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout(pad=0.3)
fig.savefig(out, metadata={"Creator": "POLAR WINDOW report", "Producer": "POLAR WINDOW report",
                           "Title": "Sun and skyline at Connecting Ridge"})
print("lit fraction by samples", round(float(np.mean(sun > sky)), 4), "samples", len(t),
      "sun el", round(sun.min(), 3), round(sun.max(), 3), "sky", round(sky.min(), 2), round(sky.max(), 2))
