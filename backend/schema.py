"""Pydantic models for level data and patches. See CLAUDE.md for the schema."""
from typing import Annotated, Literal, Union

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


class Level(BaseModel):
    name: str = "Untitled"
    tile_size: Literal[32] = 32
    width: int = Field(80, ge=10, le=400)
    height: int = Field(15, ge=5, le=50)
    physics: Physics = Physics()
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
            if e.x + e.w > self.width or e.y + e.h > self.height:
                errors.append(f"entity '{e.id}' at ({e.x},{e.y}) size {e.w}x{e.h} is outside the level")
        if errors:
            raise ValueError("; ".join(errors))
        return self


# ---- Patch ops (used from feature 2) ----
class AddOp(BaseModel):
    op: Literal["add"]
    entity: Entity


class RemoveOp(BaseModel):
    op: Literal["remove"]
    id: str


class MoveOp(BaseModel):
    op: Literal["move"]
    id: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class SetOp(BaseModel):
    op: Literal["set"]
    id: str
    key: str  # x, y, w, h, type, behaviors, or props.<name>
    value: Union[Scalar, list[str]]


class SetPhysicsOp(BaseModel):
    op: Literal["set_physics"]
    key: Literal["gravity", "jump_velocity", "run_speed"]
    value: float


PatchOp = Annotated[Union[AddOp, RemoveOp, MoveOp, SetOp, SetPhysicsOp], Field(discriminator="op")]


class Patch(BaseModel):
    explanation: str = ""
    ops: list[PatchOp]
