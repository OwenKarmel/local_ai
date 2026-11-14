"""Pydantic models for level data and patches. See CLAUDE.md for the schema."""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

EntityType = Literal["platform", "spikes", "lava", "enemy", "coin", "double_jump", "goal"]
Scalar = Union[bool, int, float, str]


class Physics(BaseModel):
    gravity: float = Field(1200, gt=0, le=5000)
    jump_velocity: float = Field(560, gt=0, le=2000)
    run_speed: float = Field(200, gt=0, le=1000)


class Spawn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


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


class Level(BaseModel):
    name: str = "Untitled"
    tile_size: Literal[32] = 32
    width: int = Field(80, ge=10, le=400)
    height: int = Field(15, ge=5, le=50)
    physics: Physics = Physics()
    abilities: dict[str, dict] = {}  # settings for model-written abilities in mechanics.js (task 6); none are pre-written
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
    changes: dict  # partial Entity: any of x, y, w, h, behaviors, props (props merge key by key)


class SetPhysics(BaseModel):
    op: Literal["set_physics"]
    key: Literal["gravity", "jump_velocity", "run_speed"]
    value: float


class SetAbility(BaseModel):
    op: Literal["set_ability"]
    ability: str
    settings: dict


LowLevelOp = Annotated[Union[AddEntity, RemoveEntity, UpdateEntity, SetPhysics, SetAbility], Field(discriminator="op")]


class LowLevelPatch(BaseModel):
    ops: list[LowLevelOp]
