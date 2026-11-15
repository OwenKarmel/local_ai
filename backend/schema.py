"""Pydantic models for level data and patches. See CLAUDE.md for the schema."""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

EntityType = Literal["platform", "spikes", "lava", "enemy", "coin", "double_jump", "grow", "goal"]
Scalar = Union[bool, int, float, str]


class Physics(BaseModel):
    gravity: float = Field(1200, gt=0, le=5000)
    jump_velocity: float = Field(560, gt=0, le=2000)
    run_speed: float = Field(200, gt=0, le=1000)


class Spawn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
# Looping visual effects any object can have (frontend/looks.js). Visual only: they never change gameplay.
LookEffect = Literal["pulse", "spin", "wobble", "bob", "flicker", "blink", "rainbow", "sparkle", "trail", "fade_far"]


class Look(BaseModel):
    """Visual-only look of one object. None = default. Applied live by frontend/looks.js."""
    top_tint: Optional[HexColor] = None   # recolor only the top row of a platform/hazard (grass, lava surface)
    body_tint: Optional[HexColor] = None  # recolor only the rows below the top (dirt)
    scale: Optional[float] = Field(None, ge=0.25, le=3)    # art size multiplier (enemies: body scales too)
    scale_x: Optional[float] = Field(None, ge=0.25, le=3)  # extra stretch: wider / thinner
    scale_y: Optional[float] = Field(None, ge=0.25, le=3)  # extra stretch: taller / shorter
    alpha: Optional[float] = Field(None, ge=0.1, le=1)     # 1 = opaque
    flip_y: Optional[bool] = None
    glow: Optional[HexColor] = None       # glow / outline color
    effects: list[LookEffect] = []


class PlayerLook(Look):
    sprite: Optional[str] = None  # catalog name; None = default player art
    tint: Optional[HexColor] = None


SceneWeather = Literal["rain", "snow", "leaves", "stars", "bubbles", "embers", "fog", "clouds", "confetti"]
SceneFilter = Literal["none", "grayscale", "sepia", "negative", "vintage", "night_vision"]


class SceneLook(BaseModel):
    """Whole-screen look. None = default."""
    background: Optional[Literal["default", "dusk", "moon"]] = None
    sky: Optional[HexColor] = None          # sky color (top of the gradient)
    sky_bottom: Optional[HexColor] = None   # bottom of the sky gradient (default: same as sky)
    scenery: Optional[bool] = None          # show the clouds/hills background art (default true)
    scenery_tint: Optional[HexColor] = None # recolor the background hills/clouds
    overlay: Optional[HexColor] = None      # translucent color laid over everything (night, sunset, underwater)
    overlay_alpha: Optional[float] = Field(None, ge=0, le=0.8)
    weather: list[SceneWeather] = []
    weather_color: Optional[HexColor] = None
    filter: Optional[SceneFilter] = None
    hue_shift: Optional[float] = Field(None, ge=-180, le=180)  # degrees; 180 = swap colors around
    saturation: Optional[float] = Field(None, ge=-1, le=1)     # -1 gray .. 0 normal .. 1 vivid
    brightness: Optional[float] = Field(None, ge=0.3, le=1.7)  # 1 = normal
    pixelate: Optional[float] = Field(None, ge=0, le=8)        # 0 = off; retro look
    zoom: Optional[float] = Field(None, ge=1, le=2)            # camera zoom (1 = normal)


ReactionEvent = Literal["jump", "land", "step", "hurt", "die", "coin", "powerup", "stomp", "enemy_defeated", "win"]
ReactionEffect = Literal["shake", "flash", "sparkles", "confetti", "burst", "ring", "zoom_bump", "spin", "squash", "blink", "mark"]


class Reaction(BaseModel):
    """When `event` happens, play `effect` at the object involved (spin/squash/blink act on that object)."""
    event: ReactionEvent
    effect: ReactionEffect
    color: Optional[HexColor] = None
    size: float = Field(1, ge=0.3, le=3)


class Entity(BaseModel):
    id: str = Field(min_length=1)
    type: EntityType
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(1, ge=1)
    h: int = Field(1, ge=1)
    behaviors: list[str] = []
    props: dict[str, Scalar] = {}
    sprite: Optional[str] = None  # name from frontend/assets/catalog.json; unknown names fall back to the type default
    tint: Optional[str] = None    # hex color like "#3399ff"
    look: Optional[Look] = None   # extra visual-only settings (size, glow, effects, ...)


class Level(BaseModel):
    name: str = "Untitled"
    tile_size: Literal[32] = 32
    width: int = Field(80, ge=10, le=400)
    height: int = Field(15, ge=5, le=50)
    physics: Physics = Physics()
    abilities: dict[str, dict] = {}  # settings for model-written abilities in mechanics.js (task 6); none are pre-written
    player_look: PlayerLook = PlayerLook()
    scene: SceneLook = SceneLook()
    reactions: list[Reaction] = Field([], max_length=16)
    spawn: Spawn
    entities: list[Entity]

    @model_validator(mode="after")
    def check_level(self):
        errors = []
        if self.spawn.x >= self.width or self.spawn.y >= self.height:
            errors.append(f"spawn ({self.spawn.x},{self.spawn.y}) is outside the {self.width}x{self.height} level")
        seen = set()
        for e in self.entities:
            if e.id in seen:
                errors.append(f"duplicate entity id '{e.id}'")
            seen.add(e.id)
            if e.x + e.w > self.width:
                errors.append(f"{e.id} ends at x {e.x + e.w} but the level is {self.width} wide; "
                              f"set w <= {max(1, self.width - e.x)} or x <= {max(0, self.width - e.w)}")
            if e.y + e.h > self.height:
                errors.append(f"{e.id} ends at y {e.y + e.h} but the level is {self.height} tall; "
                              f"set h <= {max(1, self.height - e.y)} or y <= {max(0, self.height - e.h)}")
        if errors:
            raise ValueError("; ".join(errors))
        return self


# ---- LowLevelOp: the concrete ops the backend returns and the frontend applies live (plan.md contract) ----
class AddEntity(BaseModel):
    op: Literal["add_entity"]
    entity: Entity


class RemoveEntity(BaseModel):
    op: Literal["remove_entity"]
    id: str


class UpdateEntity(BaseModel):
    op: Literal["update_entity"]
    id: str
    changes: dict  # partial Entity: any of x, y, w, h, behaviors, props (merge key by key), sprite, tint, look (whole)


class SetPhysics(BaseModel):
    op: Literal["set_physics"]
    key: Literal["gravity", "jump_velocity", "run_speed"]
    value: float


class SetAbility(BaseModel):
    op: Literal["set_ability"]
    ability: str
    settings: dict


class SetPlayerLookOp(BaseModel):
    op: Literal["set_player_look"]
    look: PlayerLook  # the full new player look


class SetSceneOp(BaseModel):
    op: Literal["set_scene"]
    scene: SceneLook  # the full new scene look


class SetReactionsOp(BaseModel):
    op: Literal["set_reactions"]
    reactions: list[Reaction]  # the full new list


LowLevelOp = Annotated[Union[AddEntity, RemoveEntity, UpdateEntity, SetPhysics, SetAbility, SetPlayerLookOp, SetSceneOp,
                             SetReactionsOp], Field(discriminator="op")]


class LowLevelPatch(BaseModel):
    ops: list[LowLevelOp]
