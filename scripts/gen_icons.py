"""One-off script to generate the app icon (a stylized crown, KOM Hunter's
"take the crown" theme in Strava's brand orange) at the sizes browsers and
iOS/Android home screens expect. Not a runtime dependency -- run locally
with Pillow installed, commit the resulting PNGs/ICO, done.

    pip install Pillow
    python scripts/gen_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

BG = (15, 17, 21, 255)  # #0f1115, matches the app's dark theme
CROWN = (252, 82, 0, 255)  # #fc5200, Strava brand orange
JEWEL = (255, 214, 130, 255)

# Crown silhouette in a 100x100 box: band across the bottom, three points
# on top (tallest in the middle), small "jewel" balls on each tip.
CROWN_POINTS = [
    (20, 78),
    (20, 65),
    (18, 45),
    (30, 58),
    (50, 32),
    (70, 58),
    (82, 45),
    (80, 65),
    (80, 78),
]
JEWEL_TIPS = [(18, 45), (50, 32), (82, 45)]

OUT_DIR = Path(__file__).resolve().parent.parent / "static"


def make_icon(size: int, corner_ratio: float = 0.22) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * corner_ratio), fill=BG)

    pad = size * 0.08
    content = size - 2 * pad

    def pt(x, y):
        return (pad + x * content / 100, pad + y * content / 100)

    draw.polygon([pt(x, y) for x, y in CROWN_POINTS], fill=CROWN)

    jewel_r = content * 0.055
    for jx, jy in JEWEL_TIPS:
        cx, cy = pt(jx, jy)
        draw.ellipse([cx - jewel_r, cy - jewel_r, cx + jewel_r, cy + jewel_r], fill=JEWEL)

    return img


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    make_icon(512).save(OUT_DIR / "icon-512.png")
    make_icon(192).save(OUT_DIR / "icon-192.png")
    make_icon(180).save(OUT_DIR / "apple-touch-icon.png")
    make_icon(64).save(
        OUT_DIR / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
    )
    print(f"Wrote icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
