from __future__ import annotations

from ..schema import Atypicality, Ceiling, Envelope, Opening, RoomType, Tier


def rect(w: float, d: float) -> list[tuple[float, float]]:
    """CCW rectangle with wall 0 along the bottom (y=0), wall 1 on the right,
    wall 2 along the top, wall 3 on the left."""
    return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]


def door(wall: int, t: float, width: float = 2.67) -> Opening:  # 2'8" door
    return Opening(kind="door", wall=wall, t=t, width=width)


def window(wall: int, t: float, width: float = 3.0) -> Opening:
    return Opening(kind="window", wall=wall, t=t, width=width)


def env(
    id: str,
    room_type: RoomType,
    vertices: list[tuple[float, float]],
    openings: list[Opening],
    tier: Tier,
    brief: str,
    ceiling: Ceiling | None = None,
    declared_extraneous: tuple[str, ...] = (),
) -> Envelope:
    return Envelope(
        id=id,
        room_type=room_type,
        vertices=vertices,
        openings=openings,
        ceiling=ceiling or Ceiling(),
        atypicality=Atypicality(
            tier=tier, brief=brief, declared_extraneous=list(declared_extraneous)
        ),
    )
