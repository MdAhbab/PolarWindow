"""Figure: two screens taken by `npm run screens` (desktop 1440 px, dark theme), cropped.

Run `npm run screens` in frontend/ first; it writes frontend/e2e/__screens__/. Writes
docs/report/fig-screen-surface.png and docs/report/fig-screen-launch.png and records the crop
boxes in out/fig_screens.txt. Pixels are not edited; only the crop is chosen here.
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
SCREENS = HERE.parents[2] / "frontend" / "e2e" / "__screens__"
CROPS = {
    # name: (source screen, (left, top, right, bottom) in screen pixels)
    "fig-screen-surface.png": ("surface-im-2.desktop.png", (0, 250, 1440, 1215)),
    "fig-screen-launch.png": ("launch-griffin-1-calendar.desktop.png", (0, 470, 1440, 1400)),
}

lines = []
for out, (src, box) in CROPS.items():
    im = Image.open(SCREENS / src).convert("RGB")
    im.crop(box).save(REPORT / out, optimize=True)
    lines.append(f"{out}: {src} {im.size} crop {box}")
(HERE / "out").mkdir(exist_ok=True)
(HERE / "out" / "fig_screens.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
