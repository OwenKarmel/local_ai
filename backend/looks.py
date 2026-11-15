"""Visual-only intent ops: set_look (any object or group), set_scene (whole screen), add/remove_reaction (event -> effect).

None of these change gameplay (no geometry, physics or hitboxes except an enemy's body following its size), so they
never need the playability checker. Applied live by frontend/looks.js.
"""
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .schema import LookEffect, ReactionEffect, ReactionEvent, SceneFilter, SceneWeather

_CATALOG = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "catalog.json"


def _catalog() -> dict[str, dict]:
    try:
        return {s["name"]: s for s in json.loads(_CATALOG.read_text())["sprites"]}
    except (OSError, ValueError, KeyError):
        return {}


CATALOG = _catalog()
SPRITE_NAMES = sorted(n for n, s in CATALOG.items() if s.get("type") not in ("background",) and not n.startswith("bg_"))

# Basic color words -> hex, so "purple" works as well as "#8e44ad"; also used to name a hex in the spoken reply.
COLORS = {
    "red": "#e53935", "dark red": "#8b1a1a", "orange": "#ff8c1a", "yellow": "#ffd92e", "gold": "#ffc107",
    "lime": "#9be22d", "green": "#3cb44b", "dark green": "#1e6b2e", "teal": "#1fb5a8", "cyan": "#2ee6e6",
    "light blue": "#7fc8ff", "blue": "#2f6bff", "navy": "#1a2a6c", "purple": "#8e44ad", "violet": "#b266ff",
    "magenta": "#e040fb", "pink": "#ff6fb5", "hot pink": "#ff2d95", "brown": "#8b5a2b", "tan": "#d2b48c",
    "beige": "#f0dcb4", "white": "#ffffff", "silver": "#c0c0c0", "gray": "#808080", "grey": "#808080",
    "dark gray": "#404040", "black": "#111111", "sky blue": "#87ceeb", "lavender": "#c8b4ff", "mint": "#9ff0c8",
    "peach": "#ffbf94", "crimson": "#c2183c", "turquoise": "#30d5c8", "indigo": "#4b0082", "coral": "#ff7f50",
}


def to_hex(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("", "none", "null", "default"):
        return None
    if s.startswith("#") and len(s) == 4:  # #abc -> #aabbcc
        s = "#" + "".join(c * 2 for c in s[1:])
    if len(s) == 6 and all(c in "0123456789abcdef" for c in s):
        s = "#" + s
    if len(s) == 7 and s[0] == "#" and all(c in "0123456789abcdef" for c in s[1:]):
        return s
    if s.replace("_", " ") in COLORS:
        return COLORS[s.replace("_", " ")]
    raise ValueError(f"'{v}' is not a color; use a hex color like #8e44ad or a basic color word")


def color_name(hexv: str) -> str:
    """Nearest basic color word for a hex (for the spoken reply)."""
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    def d(h):
        R, G, B = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return (r - R) ** 2 + (g - G) ** 2 + (b - B) ** 2
    return min((n for n in COLORS if n != "grey"), key=lambda n: d(COLORS[n]))


def _colors(*fields):
    """Validator that turns color words / short hex into #rrggbb for the given fields."""
    return field_validator(*fields, mode="before")(lambda v: to_hex(v) if v is not None else None)


Hex = Optional[str]


class SetLook(BaseModel):
    op: Literal["set_look"]
    target: str = Field(description="an object id, or a group: player, enemies, coins, platforms, ground, "
                                    "floating_platforms, spikes, lava, hazards, powerups, goals, everything")
    reset: bool = Field(False, description="true = back to the default look first")
    sprite: Optional[str] = Field(None, description="catalog sprite name")
    tint: Hex = Field(None, description="recolor, hex like #ff8c1a")
    top_tint: Hex = Field(None, description="platforms/lava: recolor only the top row (grass, lava surface)")
    body_tint: Hex = Field(None, description="platforms: recolor only the rows under the top (dirt)")
    scale: Optional[float] = Field(None, ge=0.25, le=3, description="size, 1 = normal")
    scale_x: Optional[float] = Field(None, ge=0.25, le=3, description="width stretch, 1 = normal")
    scale_y: Optional[float] = Field(None, ge=0.25, le=3, description="height stretch, 1 = normal")
    alpha: Optional[float] = Field(None, ge=0.1, le=1, description="opacity, 1 = solid, 0.4 = see-through")
    flip_y: Optional[bool] = None
    glow: Hex = Field(None, description="glow or outline color")
    effects: list[Literal[LookEffect, "none"]] = Field([], description="looping effects to add; ['none'] clears them")
    _c = _colors("tint", "top_tint", "body_tint", "glow")


class SetScene(BaseModel):
    op: Literal["set_scene"]
    reset: bool = Field(False, description="true = back to the default scene first")
    sky: Hex = None
    sky_bottom: Hex = None
    scenery: Optional[bool] = Field(None, description="show the background hills and clouds")
    scenery_tint: Hex = None
    overlay: Hex = Field(None, description="translucent color over everything")
    overlay_alpha: Optional[float] = Field(None, ge=0, le=0.8)
    weather: list[Literal[SceneWeather, "none"]] = Field([], description="replaces the current weather; ['none'] clears it")
    weather_color: Hex = None
    filter: Optional[SceneFilter] = None
    hue_shift: Optional[float] = Field(None, ge=-180, le=180)
    saturation: Optional[float] = Field(None, ge=-1, le=1)
    brightness: Optional[float] = Field(None, ge=0.3, le=1.7)
    pixelate: Optional[float] = Field(None, ge=0, le=8)
    zoom: Optional[float] = Field(None, ge=1, le=2)
    _c = _colors("sky", "sky_bottom", "scenery_tint", "overlay", "weather_color")


class AddReaction(BaseModel):
    op: Literal["add_reaction"]
    event: ReactionEvent
    effect: ReactionEffect
    color: Hex = None
    size: float = Field(1, ge=0.3, le=3)
    _c = _colors("color")


class RemoveReaction(BaseModel):
    op: Literal["remove_reaction"]
    event: Literal[ReactionEvent, "all"] = "all"
    effect: Literal[ReactionEffect, "all"] = "all"


GROUPS = {
    "enemies": ("enemy",), "coins": ("coin",), "spikes": ("spikes",), "lava": ("lava",), "hazards": ("spikes", "lava"),
    "powerups": ("double_jump", "grow"), "pickups": ("coin", "double_jump", "grow"), "goals": ("goal",),
    "platforms": ("platform",),
}
GROUP_NAMES = ["player", *GROUPS, "ground", "floating_platforms", "everything"]
AREA_TYPES = ("platform", "spikes", "lava")
SCALE_LIMITS = {"player": (0.4, 2.5), "enemy": (0.4, 2.5)}  # enemy bodies grow with their art
LOOK_FIELDS = ("top_tint", "body_tint", "scale", "scale_x", "scale_y", "alpha", "flip_y", "glow")


def look_targets(ed, target: str) -> tuple[list[dict], bool, str] | None:
    """(entities, includes_player, spoken name) for a target id or group, or None if unknown."""
    ents, H = ed.ents, ed.d["height"]
    if target == "player":
        return [], True, "you"
    if target == "everything":
        return list(ents), True, "everything"
    if target in GROUPS:
        return [e for e in ents if e["type"] in GROUPS[target]], False, "the " + target.replace("_", " ")
    if target in ("ground", "floating_platforms"):
        ground = target == "ground"
        sel = [e for e in ents if e["type"] == "platform" and (e["y"] + e["h"] >= H) == ground]
        return sel, False, "the ground" if ground else "the floating platforms"
    e = ed.get(target)
    if e:
        return [e], False, e["id"]
    return None


def _merge_look(cur: dict, op: SetLook, kind: str, ed, where: str) -> dict:
    cur = dict(cur or {})
    lo, hi = SCALE_LIMITS.get(kind, (0.25, 3))
    for k in LOOK_FIELDS:
        v = getattr(op, k)
        if v is None:
            continue
        if k.startswith("scale"):
            c = min(max(v, lo), hi)
            if c != v:
                ed.repairs.append(f"{where}: {kind} {k} clamped {v:g} -> {c:g} (allowed {lo:g}-{hi:g})")
            v = c
        cur[k] = v
    if op.effects:
        eff = [] if "none" in op.effects else list(cur.get("effects") or [])
        cur["effects"] = eff + [x for x in op.effects if x != "none" and x not in eff]
    return cur


def describe_look(op: SetLook) -> str:
    """'purple and bigger', 'look like a snail with a shell', ... for the spoken reply."""
    bits = []
    if op.reset and not any(getattr(op, k) for k in ("sprite", "tint", *LOOK_FIELDS)) and not op.effects:
        return "normal again"
    if op.sprite:
        d = CATALOG.get(op.sprite, {}).get("description", op.sprite.replace("_", " "))
        bits.append("look like a " + d.split(",")[0].split("(")[0].split(":")[0].strip())
    for k, word in (("tint", ""), ("top_tint", "on top"), ("body_tint", "underneath")):
        if getattr(op, k):
            bits.append(f"{color_name(getattr(op, k))} {word}".strip())
    if op.scale:
        bits.append("bigger" if op.scale > 1 else "smaller")
    if op.scale_x:
        bits.append("wider" if op.scale_x > 1 else "thinner")
    if op.scale_y:
        bits.append("taller" if op.scale_y > 1 else "shorter")
    if op.alpha is not None and op.alpha < 1:
        bits.append("see-through")
    if op.flip_y:
        bits.append("upside down")
    if op.glow:
        bits.append(f"glow {color_name(op.glow)}")
    fx = [x for x in op.effects if x != "none"]
    if fx:
        bits.append(" and ".join(x.replace("_", " ") for x in fx[:2]))
    if "none" in op.effects and not fx:
        bits.append("without effects")
    if not bits:
        return ""
    return bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + " and " + bits[-1]


def set_look(ed, op: SetLook, where: str):
    t = look_targets(ed, op.target)
    if t is None:
        ed.errors.append(f"{where}: unknown target '{op.target}'. Use an object id or a group: {', '.join(GROUP_NAMES)}")
        return
    ents, with_player, name = t
    if op.sprite is not None and op.sprite not in CATALOG:
        ed.errors.append(f"{where}: unknown sprite '{op.sprite}'. Use a name from the SPRITES list")
        return
    if op.sprite and op.target == "everything":
        ed.errors.append(f"{where}: give each kind of object its own sprite (one set_look per group), not 'everything'")
        return
    changed = False
    if with_player:
        pl = {} if op.reset else dict(ed.d.get("player_look") or {})
        before = dict(ed.d.get("player_look") or {})
        if op.sprite:
            pl["sprite"] = op.sprite
        if op.tint:
            pl["tint"] = op.tint
        base = {k: v for k, v in pl.items() if k not in ("sprite", "tint")}
        merged = _merge_look(base, op, "player", ed, where)
        pl = {**{k: pl.get(k) for k in ("sprite", "tint")}, **merged}
        ed.d["player_look"] = pl
        changed |= _norm(pl) != _norm(before)
    for e in ents:
        before = (e.get("sprite"), e.get("tint"), _norm(e.get("look")))
        if op.reset:
            e["sprite"] = e["tint"] = e["look"] = None
        if op.sprite:
            e["sprite"] = op.sprite
        if op.tint:
            e["tint"] = op.tint
        e["look"] = _merge_look(e.get("look"), op, e["type"], ed, where) or None
        if (e.get("sprite"), e.get("tint"), _norm(e.get("look"))) != before:
            changed = True
    if not ents and not with_player:
        ed.errors.append(f"{where}: there are no {op.target} in this level")
        return
    if not changed:
        ed.repairs.append(f"{where}: {op.target} already look like that, so nothing changed")
        return
    desc = describe_look(op)
    ed.done.append(f"made {name} {desc}" if desc else f"changed how {name} look")


def _norm(look: dict | None) -> dict:
    return {k: v for k, v in (look or {}).items() if v not in (None, [], False)}


def set_scene(ed, op: SetScene, where: str):
    before = _norm(ed.d.get("scene"))
    sc = {} if op.reset else dict(ed.d.get("scene") or {})
    words = []
    for k in SetScene.model_fields:
        if k in ("op", "reset", "weather"):
            continue
        v = getattr(op, k)
        if v is not None:
            sc[k] = v
    if op.weather:
        sc["weather"] = [w for w in dict.fromkeys(op.weather) if w != "none"]
        words.append(("added " + " and ".join(sc["weather"])) if sc["weather"] else "cleared the weather")
    ed.d["scene"] = sc
    if _norm(sc) == before:
        ed.repairs.append(f"{where}: the scene already looks like that, so nothing changed")
        return
    if op.sky or op.sky_bottom:
        words.append(f"made the sky {color_name(op.sky or op.sky_bottom)}")
    if op.overlay and (op.overlay_alpha or 0) > 0:
        words.append(f"tinted everything {color_name(op.overlay)}")
    if op.filter and op.filter != "none":
        words.append(f"turned on the {op.filter.replace('_', ' ')} filter")
    if op.zoom:
        words.append("zoomed in" if op.zoom > 1 else "reset the zoom")
    if op.pixelate:
        words.append("pixelated the screen")
    if op.reset and len(words) == 0:
        words.append("reset the scene")
    ed.done.append(" and ".join(words[:2]) if words else "changed the scene")


EVENT_WORDS = {"jump": "you jump", "land": "you land", "step": "you walk", "hurt": "you get hurt", "die": "you die",
               "coin": "you grab a coin", "powerup": "you grab a powerup", "stomp": "you stomp an enemy",
               "enemy_defeated": "an enemy is defeated", "win": "you win"}


def add_reaction(ed, op: AddReaction, where: str):
    rs = [r for r in (ed.d.get("reactions") or []) if not (r["event"] == op.event and r["effect"] == op.effect)]
    if len(rs) >= 16:
        ed.errors.append(f"{where}: at most 16 reactions; remove one first (remove_reaction)")
        return
    rs.append({"event": op.event, "effect": op.effect, "color": op.color, "size": op.size})
    ed.d["reactions"] = rs
    ed.done.append(f"added {op.effect.replace('_', ' ')} when {EVENT_WORDS[op.event]}")


def remove_reaction(ed, op: RemoveReaction, where: str):
    rs = ed.d.get("reactions") or []
    keep = [r for r in rs if not ((op.event in ("all", r["event"])) and (op.effect in ("all", r["effect"])))]
    if len(keep) == len(rs):
        ed.repairs.append(f"{where}: no matching reaction to remove")
        return
    ed.d["reactions"] = keep
    ed.done.append("removed " + ("all effects" if op.event == "all" else f"the effects when {EVENT_WORDS[op.event]}"))


def restrict_schema(defs: dict, all_ids: list[str]):
    """Limit set_look targets to real ids/groups and sprites to catalog names (grammar-constrained decoding)."""
    defs["SetLook"]["properties"]["target"]["enum"] = GROUP_NAMES + [i for i in all_ids if i not in GROUP_NAMES]
    sp = defs["SetLook"]["properties"]["sprite"]
    sp.pop("anyOf", None)
    sp.update({"anyOf": [{"type": "string", "enum": SPRITE_NAMES}, {"type": "null"}]})
