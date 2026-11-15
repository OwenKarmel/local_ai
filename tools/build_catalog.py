"""Copy the sprites we use from Kenney's "New Platformer Pack" (CC0) and write the sprite catalog.

    python tools/build_catalog.py /path/to/extracted/kenney_new-platformer-pack

Needs Pillow (only to make tintable white variants). Outputs:
    frontend/assets/sprites/*.png + License.txt
    frontend/assets/catalog.json   (full catalog, loaded by the game)
    frontend/assets/catalog.txt    (name: description, for model prompts)
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import big_player  # tools/big_player.py (this folder is on sys.path when run as a script)

PACK = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "assets"
SPR = OUT / "sprites"
SRC = {"c": PACK / "Sprites/Characters/Default", "e": PACK / "Sprites/Enemies/Default",
       "t": PACK / "Sprites/Tiles/Default", "b": PACK / "Sprites/Backgrounds/Default"}
entries, used = [], set()


def use(kind: str, fname: str) -> str:
    src = SRC[kind] / fname
    assert src.exists(), src
    shutil.copyfile(src, SPR / fname)
    used.add(fname)
    return fname


def size(fname: str) -> list[int]:
    return list(Image.open(SPR / fname).size)


def add(name, type_, file, desc, **extra):
    entries.append({"name": name, "type": type_, "file": file, "description": desc, "size": size(file), **extra})


def anim(kind, frames, fps):
    return {"frames": [use(kind, f) for f in frames], "fps": fps}


# ---- players (128x128 frames) ----
for color in ["green", "pink", "yellow", "purple", "beige"]:
    p = f"character_{color}_"
    add(f"player_{color}", "player", use("c", p + "idle.png"), f"{color} alien astronaut, the player character", scale=0.375,
        animations={"idle": anim("c", [p + "idle.png"], 1), "run": anim("c", [p + "walk_a.png", p + "walk_b.png"], 8),
                    "jump": anim("c", [p + "jump.png"], 1), "hit": anim("c", [p + "hit.png"], 1)})

# Grown player for the grow power-up: taller green alien (CC0 derivative, see tools/big_player.py).
big = big_player.make(SPR, "green")
used.update(big)
bf = {n.removeprefix("character_big_green_").removesuffix(".png"): n for n in big}
add("player_big_green", "player_big", bf["idle"], "tall green alien astronaut with antenna, star badge and belt: the grown player (grow power-up)",
    scale=0.375, animations={"idle": {"frames": [bf["idle"]], "fps": 1}, "run": {"frames": [bf["walk_a"], bf["walk_b"]], "fps": 8},
                             "jump": {"frames": [bf["jump"]], "fps": 1}, "hit": {"frames": [bf["hit"]], "fps": 1}})

# ---- platform tilesets (64x64 tiles) ----
LOOK = {"grass": "green grass on brown dirt", "dirt": "brown dirt", "sand": "yellow desert sand", "snow": "white snow on ice-blue ground",
        "stone": "grey stone", "purple": "purple alien grass"}
for theme, look in LOOK.items():
    t = f"terrain_{theme}_"
    tiles = {k: use("t", t + v + ".png") for k, v in {
        "top_left": "block_top_left", "top": "block_top", "top_right": "block_top_right",
        "left": "block_left", "center": "block_center", "right": "block_right",
        "h_left": "horizontal_left", "h_middle": "horizontal_middle", "h_right": "horizontal_right", "single": "block"}.items()}
    add(f"platform_{theme}", "tile", tiles["top"], f"platform and ground tiles: {look}", scale=0.5, tiles=tiles)

# ---- hazards ----
add("spikes", "hazard", use("t", "spikes.png"), "grey metal floor spikes", scale=0.5)
add("spike_block", "hazard", use("t", "block_spikes.png"), "block covered in spikes", scale=0.5)
add("saw", "hazard", use("t", "saw.png"), "grey circular saw blade", scale=0.5)
add("lava", "hazard", use("t", "lava_top.png"), "orange bubbling lava", scale=0.5,
    tiles={"top": "lava_top.png", "center": use("t", "lava.png")})
add("water", "hazard", use("t", "water_top.png"), "blue water (still deadly, looks like water)", scale=0.5,
    tiles={"top": "water_top.png", "center": use("t", "water.png")})

# ---- enemies (64x64, art faces left) ----
ENEMIES = [
    ("enemy_slime_purple", "slime_normal_walk_a.png", ["slime_normal_walk_a.png", "slime_normal_walk_b.png"], "purple slime blob (default enemy)"),
    ("enemy_slime_fire", "slime_fire_walk_a.png", ["slime_fire_walk_a.png", "slime_fire_walk_b.png"], "red slime with a flame on its head"),
    ("enemy_slime_spike", "slime_spike_walk_a.png", ["slime_spike_walk_a.png", "slime_spike_walk_b.png"], "slime with a spiky back"),
    ("enemy_mouse", "mouse_walk_a.png", ["mouse_walk_a.png", "mouse_walk_b.png"], "grey mouse"),
    ("enemy_ladybug", "ladybug_walk_a.png", ["ladybug_walk_a.png", "ladybug_walk_b.png"], "red ladybug with black spots"),
    ("enemy_snail", "snail_walk_a.png", ["snail_walk_a.png", "snail_walk_b.png"], "snail with a shell"),
    ("enemy_frog", "frog_idle.png", ["frog_idle.png", "frog_jump.png"], "green frog"),
    ("enemy_bee", "bee_a.png", ["bee_a.png", "bee_b.png"], "yellow striped bee"),
    ("enemy_fly", "fly_a.png", ["fly_a.png", "fly_b.png"], "black fly with wings"),
    ("enemy_worm", "worm_normal_move_a.png", ["worm_normal_move_a.png", "worm_normal_move_b.png"], "small pink worm"),
]
for name, file, frames, desc in ENEMIES:
    add(name, "enemy", use("e", file), desc, scale=0.5, animations={"walk": anim("e", frames, 5)})

# ---- coins ----
for metal in ["gold", "silver", "bronze"]:
    add(f"coin_{metal}", "coin", use("t", f"coin_{metal}.png"), f"{metal} coin", scale=0.5,
        animations={"spin": anim("t", [f"coin_{metal}.png", f"coin_{metal}_side.png"], 4)})
for c in ["blue", "green", "red", "yellow"]:
    add(f"gem_{c}", "coin", use("t", f"gem_{c}.png"), f"{c} gem (collectible, counts as a coin)", scale=0.5)

# ---- power-ups ----
add("powerup_star", "powerup", use("t", "star.png"), "gold star (default double-jump power-up)", scale=0.5)
add("powerup_heart", "powerup", use("t", "heart.png"), "red heart", scale=0.5)
add("powerup_spring", "powerup", use("t", "spring.png"), "metal spring", scale=0.5)
add("powerup_mushroom_red", "powerup", use("t", "mushroom_red.png"), "red mushroom (default grow power-up)", scale=0.5)
add("powerup_mushroom_brown", "powerup", use("t", "mushroom_brown.png"), "brown mushroom", scale=0.5)

# ---- goal ----
for c in ["green", "red", "blue", "yellow"]:
    add(f"flag_{c}", "goal", use("t", f"flag_{c}_a.png"), f"{c} goal flag on a pole", scale=1.0,
        animations={"wave": anim("t", [f"flag_{c}_a.png", f"flag_{c}_b.png"], 4)})
add("sign_exit", "goal", use("t", "sign_exit.png"), "wooden exit sign", scale=1.0)

# ---- projectiles ----
add("fireball_orange", "projectile", use("t", "fireball.png"), "orange fireball (default projectile)", scale=0.5, trail="#ff9a2e")
# Tintable white ball derived from the fireball art (CC0 derivative): grayscale, brightened.
fb = Image.open(SPR / "fireball.png").convert("RGBA")
r, g, b, a = fb.split()
lum = Image.merge("RGB", (r, g, b)).convert("L").point(lambda v: min(255, int(v * 1.25) + 60))
Image.merge("RGBA", (lum, lum, lum, a)).save(SPR / "ball_white.png")
used.add("ball_white.png")
add("ball_white", "projectile", "ball_white.png", "white energy ball; set tint to color it", scale=0.5)
add("iceball_blue", "projectile", "ball_white.png", "icy blue ball", scale=0.5, tint="#6fd0ff")
add("fireball_red", "projectile", "ball_white.png", "red fireball", scale=0.5, tint="#ff4a3d")
add("energy_ball_purple", "projectile", "ball_white.png", "purple energy ball", scale=0.5, tint="#b46bff")
add("energy_ball_green", "projectile", "ball_white.png", "green energy ball", scale=0.5, tint="#5dff8a")
add("bomb", "projectile", use("t", "bomb.png"), "round black bomb", scale=0.5)

# ---- effects (generated; white so particles can be tinted) ----
dot = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
ImageDraw.Draw(dot).ellipse((3, 3, 12, 12), fill=(255, 255, 255, 255))
dot.filter(ImageFilter.GaussianBlur(1.2)).save(SPR / "effect_spark.png")
st = Image.open(SPR / "star.png").convert("RGBA").resize((24, 24), Image.LANCZOS)
Image.merge("RGBA", (*[st.split()[3].point(lambda v: 255)] * 3, st.split()[3])).save(SPR / "effect_star.png")
used.update({"effect_spark.png", "effect_star.png"})
add("effect_spark", "effect", "effect_spark.png", "soft white dot particle (trails, bursts)")
add("effect_star", "effect", "effect_star.png", "white star particle (sparkles)")

# ---- backgrounds ----
add("bg_sky", "background", use("b", "background_solid_sky.png"), "plain light-blue sky")
add("bg_clouds", "background", use("b", "background_clouds.png"), "cloud band")
add("bg_hills", "background", use("b", "background_color_hills.png"), "green rolling hills")

shutil.copyfile(PACK / "License.txt", SPR / "License.txt")
for f in SPR.glob("*.png"):  # drop files from older runs
    if f.name not in used:
        f.unlink()

catalog = {
    "source": "Kenney New Platformer Pack 1.1 (kenney.nl), CC0. See sprites/License.txt. ball_white.png, effect_*.png, character_big_*.png are derived/generated.",
    "defaults": {"player": "player_green", "platform": "platform_grass", "spikes": "spikes", "lava": "lava", "enemy": "enemy_slime_purple",
                 "coin": "coin_gold", "double_jump": "powerup_star", "grow": "powerup_mushroom_red", "player_big": "player_big_green", "goal": "flag_green", "projectile": "fireball_orange"},
    "sprites": entries,
}
(OUT / "catalog.json").write_text(json.dumps(catalog, indent=1) + "\n")
lines = ["# Sprite catalog: name: description. Use a name as an entity's \"sprite\". \"tint\" is any hex color like #3399ff."]
for t in ["player", "player_big", "tile", "hazard", "enemy", "coin", "powerup", "goal", "projectile"]:
    lines.append(f"[{t}]")
    lines += [f"{e['name']}: {e['description']}" for e in entries if e["type"] == t]
(OUT / "catalog.txt").write_text("\n".join(lines) + "\n")
total = sum(f.stat().st_size for f in SPR.iterdir())
print(f"{len(entries)} catalog entries, {len(used)} png files, {total / 1024:.0f} KB in {SPR}")
