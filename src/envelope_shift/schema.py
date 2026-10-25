"""Room envelope and entity schema.

This is an independent reimplementation of the representation described in
Higharc's public engineering post on their Generative Building Model
(https://www.higharc.com/blog/ai-layout-at-higharc-tokenizing-buildings).
It is built from the public description only; it is not their format.

Units: feet. Coordinates are plan-view (x, y). Envelope vertices are the
interior wall faces of the room, listed as a closed polygon. Wall i runs from
vertices[i] to vertices[(i + 1) % n].

An entity is placed relative to a supporting wall, following the published
(e_q, t_q, delta_q, s_q, rho_q) parameterization:

    wall        supporting wall index
    t           normalized position along that wall, in [0, 1]
    offset      lateral offset: distance from the wall face to the entity's
                back edge, measured along the inward normal
    width       extent along the wall
    depth       extent perpendicular to the wall, into the room
    height      vertical extent
    rotation    degrees, counter-clockwise, about the anchor point
                (the midpoint of the entity's back edge)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .failure import FailureKind, kind_from_error


class RoomType(StrEnum):
    KITCHEN = "kitchen"
    PRIMARY_BATH = "primary_bath"
    SECONDARY_BATH = "secondary_bath"
    PRIMARY_BEDROOM = "primary_bedroom"
    SECONDARY_BEDROOM = "secondary_bedroom"
    OFFICE = "office"
    GARAGE = "garage"


class Tier(StrEnum):
    """The atypicality ladder. T0 is the calibration tier."""

    T0_CALIBRATION = "T0"
    T1_PROPORTION = "T1"
    T2_NONCONVEX = "T2"
    T3_NONORTHOGONAL = "T3"
    T4_VERTICAL = "T4"
    T5_PROGRAM = "T5"


Point = tuple[float, float]


class Opening(BaseModel):
    """A door or window on a wall, positioned by normalized wall coordinate."""

    kind: Literal["door", "window"]
    wall: int = Field(ge=0)
    t: float = Field(ge=0.0, le=1.0, description="center, normalized along wall")
    width: float = Field(gt=0)
    # Doors swing into the room by default; used for door-clearance geometry.
    swing_depth: float | None = Field(default=None, gt=0)


class Ceiling(BaseModel):
    """Optional vertical constraint. Only T4 envelopes set a slope.

    A sloped ceiling is a plane: height at the anchor wall's face is `height`,
    and it drops by `slope_ft_per_ft` per foot of distance from that wall along
    the inward normal. Entities taller than the local headroom violate it.
    """

    height: float = Field(default=9.0, gt=0)
    slope_wall: int | None = None
    slope_ft_per_ft: float = Field(default=0.0, ge=0.0)
    min_height: float | None = Field(default=None, gt=0)


class Atypicality(BaseModel):
    tier: Tier
    brief: str = Field(
        description="one line on what makes this room unusual; TRANSMITTED to the model"
    )
    declared_extraneous: list[str] = Field(
        default_factory=list,
        description=(
            "entity types the experimenter declares extraneous for this room (T5 only). "
            "The scorer's answer key: HELD OUT of the prompt, never transmitted."
        ),
    )

    @property
    def note(self) -> str:
        """The model-facing brief. Kept as an alias for callers that only want a caption;
        it never includes `declared_extraneous`."""
        return self.brief


class Envelope(BaseModel):
    id: str
    room_type: RoomType
    vertices: list[Point] = Field(min_length=3)
    wall_thickness: float = Field(default=0.375, gt=0)  # 4.5" nominal
    openings: list[Opening] = Field(default_factory=list)
    ceiling: Ceiling = Field(default_factory=Ceiling)
    atypicality: Atypicality

    @field_validator("vertices")
    @classmethod
    def _closed_polygon_not_repeated(cls, v: list[Point]) -> list[Point]:
        if len(v) > 3 and v[0] == v[-1]:
            v = v[:-1]
        return v

    @model_validator(mode="after")
    def _openings_reference_real_walls(self) -> Envelope:
        n = len(self.vertices)
        for o in self.openings:
            if o.wall >= n:
                raise ValueError(f"opening references wall {o.wall}, room has {n}")
        if self.ceiling.slope_wall is not None and self.ceiling.slope_wall >= n:
            raise ValueError("ceiling.slope_wall out of range")
        return self

    @property
    def n_walls(self) -> int:
        return len(self.vertices)

    def wall(self, i: int) -> tuple[Point, Point]:
        return self.vertices[i], self.vertices[(i + 1) % self.n_walls]

    @property
    def doors(self) -> list[Opening]:
        return [o for o in self.openings if o.kind == "door"]

    @property
    def windows(self) -> list[Opening]:
        return [o for o in self.openings if o.kind == "window"]


class Entity(BaseModel):
    """A placed piece of furniture, fixture, or casework, wall-referenced."""

    type: str = Field(description="lowercase snake_case, e.g. 'bed_queen', 'toilet'")
    wall: int = Field(ge=0)
    t: float = Field(ge=0.0, le=1.0)
    offset: float = Field(ge=0.0)
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation: float = 0.0
    # Bottom of the entity above the floor. Upper cabinets, wall shelves and
    # the like are elevated; elevated entities do not block walking paths and
    # only overlap entities whose vertical range they share.
    elevation: float = Field(default=0.0, ge=0.0)

    @property
    def top(self) -> float:
        return self.elevation + self.height

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_").replace("-", "_")


class Layout(BaseModel):
    """A model's answer for one envelope, plus bookkeeping for the sweep."""

    envelope_id: str
    model: str
    entities: list[Entity] = Field(default_factory=list)
    parse_ok: bool = True
    # Why parse_ok is False: the model's reply did not parse, or no reply arrived.
    # Records written before the field existed are classified from `error`'s prefix.
    failure_kind: FailureKind | None = None
    raw: str | None = None
    error: str | None = None
    # claude_cli only: {"argv": [...], "events": [...]}, the CLI's own stream-json output,
    # stored verbatim so the call's condition can be re-derived from it (claim v8).
    cli: dict | None = None
    # sha256 of the [system, user] strings the transport actually sent (generate.prompt_sha256),
    # taken from its request. Rows written before it existed carry none: claim v9 fails them.
    prompt_sha256: str | None = None
    # OpenAI-compatible backends: what the provider's response says answered ({"model",
    # "system_fingerprint"}, each possibly None). The sweep files it under call_config.observed;
    # it is None when no response was read, and then the row has no such block.
    observed: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def _classify_legacy_failure(cls, data):
        if isinstance(data, dict) and not data.get("parse_ok", True) and data.get("failure_kind") is None:
            return {**data, "failure_kind": kind_from_error(data.get("error"))}
        return data


# JSON schema handed to generators, so every model is asked for the same shape.
ENTITY_ARRAY_SCHEMA = {
    "type": "array",
    "items": Entity.model_json_schema(),
}
