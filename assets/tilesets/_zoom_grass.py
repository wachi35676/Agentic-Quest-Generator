"""Crop the right-side grass+path zone of TilesetFloor for closer study."""
from PIL import Image, ImageDraw, ImageFont
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
TILE = 16
SCALE = 8

im = Image.open(os.path.join(ROOT, "TilesetFloor.png")).convert("RGBA")
# zone of interest: cols 11..21, rows 11..21  -> 11 cols x 11 rows
C0, C1 = 11, 22
R0, R1 = 11, 22
crop = im.crop((C0*TILE, R0*TILE, C1*TILE, R1*TILE))
big = crop.resize(((C1-C0)*TILE*SCALE, (R1-R0)*TILE*SCALE), Image.NEAREST)
draw = ImageDraw.Draw(big)
try:
    font = ImageFont.truetype("arial.ttf", 18)
except OSError:
    font = ImageFont.load_default()

cols = C1 - C0
rows = R1 - R0
for c in range(cols + 1):
    x = c * TILE * SCALE
    draw.line((x, 0, x, rows*TILE*SCALE), fill=(255,0,255,200), width=2)
for r in range(rows + 1):
    y = r * TILE * SCALE
    draw.line((0, y, cols*TILE*SCALE, y), fill=(255,0,255,200), width=2)
for r in range(rows):
    for c in range(cols):
        x = c*TILE*SCALE + 4
        y = r*TILE*SCALE + 2
        txt = f"{c+C0},{r+R0}"
        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
            draw.text((x+dx, y+dy), txt, fill=(0,0,0,255), font=font)
        draw.text((x, y), txt, fill=(255,255,0,255), font=font)
big.save(os.path.join(ROOT, "_grass_zone.png"))
print("wrote _grass_zone.png", big.size)
