"""Render TilesetFloor.png and TilesetField.png with a coordinate grid overlay
so we can identify edge/corner/path tiles by atlas coords.

Output (resized 4x for readability):
  _floor_atlas.png  – TilesetFloor with (col,row) labels
  _field_atlas.png  – TilesetField with (col,row) labels
"""
from PIL import Image, ImageDraw, ImageFont
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TILE = 16
SCALE = 4   # 16 -> 64 px

def render(src, out):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    cols, rows = w // TILE, h // TILE
    big = im.resize((w * SCALE, h * SCALE), Image.NEAREST)
    draw = ImageDraw.Draw(big)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    # grid lines
    for c in range(cols + 1):
        x = c * TILE * SCALE
        draw.line((x, 0, x, rows * TILE * SCALE), fill=(255, 0, 255, 180), width=1)
    for r in range(rows + 1):
        y = r * TILE * SCALE
        draw.line((0, y, cols * TILE * SCALE, y), fill=(255, 0, 255, 180), width=1)
    # labels: (col,row) at top-left of each cell, in 14px black-outlined yellow
    for r in range(rows):
        for c in range(cols):
            x = c * TILE * SCALE + 2
            y = r * TILE * SCALE + 1
            txt = f"{c},{r}"
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                draw.text((x+dx, y+dy), txt, fill=(0,0,0,255), font=font)
            draw.text((x, y), txt, fill=(255,255,0,255), font=font)
    big.save(out)
    print(f"wrote {out}  ({cols}x{rows} tiles, {big.size[0]}x{big.size[1]} px)")

if __name__ == "__main__":
    render(os.path.join(ROOT, "TilesetFloor.png"), os.path.join(ROOT, "_floor_atlas.png"))
    render(os.path.join(ROOT, "TilesetField.png"), os.path.join(ROOT, "_field_atlas.png"))
