"""Derive the "big" player (the grown look from the grow power-up) from a Kenney alien. CC0 derivative.

    python tools/big_player.py [color]     # default green; reads/writes frontend/assets/sprites/

Also called by build_catalog.py. Per frame: lengthen the torso (EXTRA drawn rows inserted at a row just below the arms),
then add a gold-tipped antenna, a chest star and a belt with a gold buckle. Frames go from 128x128 to 128x168.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

FRAMES = ("idle", "walk_a", "walk_b", "jump", "hit")
CUT = {"idle": 114, "walk_a": 114, "walk_b": 114, "jump": 115, "hit": 115}  # a single-run body row in every frame
EXTRA = 40  # rows of torso added
SS = 4      # supersampling for the drawn details (smooth edges like the original art)
OUTLINE = (53, 53, 65, 255)
BODY = (93, 212, 170, 255)
SHADE = (74, 195, 153, 255)  # the art's right-side shading
GOLD = (247, 201, 72, 255)
GOLD_HI = (255, 236, 150, 255)


def _run(im: Image.Image, y: int) -> tuple[int, int]:
    xs = [x for x in range(im.width) if im.getpixel((x, y))[3] > 128]
    return xs[0], xs[-1]


def _detail(size: tuple[int, int], draw) -> Image.Image:
    big = Image.new("RGBA", (size[0] * SS, size[1] * SS), (0, 0, 0, 0))
    draw(ImageDraw.Draw(big), lambda v: v * SS)
    return big.resize(size, Image.LANCZOS)


def _star(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    import math
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def make_frame(im: Image.Image, cut: int) -> Image.Image:
    w, h = im.size
    body = Image.new("RGBA", (w, h + EXTRA), (0, 0, 0, 0))
    body.paste(im.crop((0, 0, w, cut)), (0, 0))
    # Torso row drawn clean (the cut row already holds leg outlines): outline, body green, shaded right side.
    x0, x1 = _run(im, cut)
    row = Image.new("RGBA", (w, 1), (0, 0, 0, 0))
    for x in range(x0, x1 + 1):
        row.putpixel((x, 0), OUTLINE if x < x0 + 4 or x > x1 - 4 else SHADE if x > x1 - 13 else BODY)
    for i in range(EXTRA):
        body.paste(row, (0, cut + i))
    body.paste(im.crop((0, cut, w, h)), (0, cut + EXTRA))

    mid = (x0 + x1 + 1) / 2
    top = im.getbbox()[1]
    hx0, hx1 = _run(im, top + 6)
    hcx = (hx0 + hx1 + 1) / 2  # helmet center (the body can lean in walk frames)

    # antenna behind the helmet
    def antenna(d, s):
        d.line([(s(hcx), s(top + 8)), (s(hcx + 3), s(top - 13))], fill=OUTLINE, width=round(s(4)))
        d.ellipse([s(hcx + 3 - 6), s(top - 19), s(hcx + 3 + 6), s(top - 7)], fill=GOLD, outline=OUTLINE, width=round(s(2.5)))
        d.ellipse([s(hcx + 1), s(top - 16), s(hcx + 4), s(top - 13)], fill=GOLD_HI)
    out = _detail(body.size, antenna)
    out.alpha_composite(body)

    # belt + buckle at the bottom of the new torso, star on the chest
    by = cut + EXTRA - 13
    def suit(d, s):
        d.rectangle([s(x0), s(by), s(x1 + 1), s(by + 7)], fill=OUTLINE)
        d.rounded_rectangle([s(mid - 7), s(by - 2), s(mid + 7), s(by + 9)], radius=s(2.5), fill=GOLD, outline=OUTLINE, width=round(s(2)))
        d.rectangle([s(mid - 2.5), s(by + 1.5), s(mid + 2.5), s(by + 5.5)], fill=OUTLINE)
        d.polygon(_star(s(mid - 1), s(cut + EXTRA * 0.36), s(11)), fill=GOLD, outline=OUTLINE, width=round(s(1.5)))
    deco = _detail(body.size, suit)
    deco.putalpha(Image.composite(deco.getchannel("A"), Image.new("L", body.size, 0), body.getchannel("A")))  # stay inside the body
    out.alpha_composite(deco)
    return out


def make(spr_dir: Path, color: str = "green") -> list[str]:
    """Writes character_big_<color>_<frame>.png next to the source frames; returns the file names."""
    names = []
    for f in FRAMES:
        src = Image.open(spr_dir / f"character_{color}_{f}.png").convert("RGBA")
        name = f"character_big_{color}_{f}.png"
        make_frame(src, CUT[f]).save(spr_dir / name, optimize=True)
        names.append(name)
    return names


if __name__ == "__main__":
    spr = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "sprites"
    print(make(spr, sys.argv[1] if len(sys.argv) > 1 else "green"))
