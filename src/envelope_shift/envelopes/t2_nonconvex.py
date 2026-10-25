"""T2: non-convex envelopes. L, T and U shapes, alcoves, intruding columns,
notched corners.

Every polygon here is deliberately non-convex: its convex hull is at least 2%
larger than the room itself (tests/test_tiers_t23.py enforces this). All
vertex lists are CCW with wall 0 along the bottom where a room has one.
"""

from ..schema import RoomType, Tier
from ._helpers import door, env, window

T = Tier.T2_NONCONVEX


def build():
    # L-shaped: 14x16 with a 6x6 notch removed from the top-right corner.
    l_shape = [(0, 0), (14, 0), (14, 10), (8, 10), (8, 16), (0, 16)]
    # Bedroom with a 4 ft deep alcove on the top wall.
    alcove = [(0, 0), (12, 0), (12, 12), (9, 12), (9, 16), (3, 16), (3, 12), (0, 12)]
    # Kitchen with a 2x2 structural column intruding from the left wall.
    column = [(0, 0), (14, 0), (14, 14), (0, 14), (0, 8), (2, 8), (2, 6), (0, 6)]
    # T-shaped office: 6x6 entry stem below a 14x8 head. Wall 0 is the stem's
    # bottom wall; wall 4 is the full-width top wall.
    t_shape = [(4, 0), (10, 0), (10, 6), (14, 6), (14, 14), (0, 14), (0, 6), (4, 6)]
    # 22x22 garage with a 4x6 stair landing notched out of the top-left corner.
    garage_notch = [(0, 0), (22, 0), (22, 22), (4, 22), (4, 16), (0, 16)]
    # U-shaped primary bath: 14x12 wrapping a 4x6 linen closet that intrudes
    # from the middle of the top wall. Wall 2 is the top of the right lobe.
    u_shape = [(0, 0), (14, 0), (14, 12), (9, 12), (9, 6), (5, 6), (5, 12), (0, 12)]
    # 5x9 secondary bath with a 2x2 duct chase in the top-left corner.
    chase = [(0, 0), (5, 0), (5, 9), (2, 9), (2, 7), (0, 7)]
    # 12x13 secondary bedroom with a 3 ft wide chimney breast intruding 2 ft
    # from the middle of the bottom (exterior) wall. Walls 0 and 4 flank it.
    chimney = [(0, 0), (5, 0), (5, 2), (8, 2), (8, 0), (12, 0), (12, 13), (0, 13)]
    return [
        env("t2_pbed_L", RoomType.PRIMARY_BEDROOM, l_shape,
            [door(0, 0.15), window(4, 0.5, 3.0)], T, "L-shaped primary bedroom"),
        env("t2_sbed_alcove", RoomType.SECONDARY_BEDROOM, alcove,
            [door(0, 0.2), window(4, 0.5, 3.0)], T, "bedroom with 6x4 alcove"),
        env("t2_kitchen_column", RoomType.KITCHEN, column,
            [door(0, 0.2), window(2, 0.5, 4.0)], T, "kitchen with intruding column"),
        env("t2_office_T", RoomType.OFFICE, t_shape,
            [door(0, 0.5), window(4, 0.5, 4.0)], T, "T-shaped office entered through a 6 ft stem"),
        env("t2_garage_notch", RoomType.GARAGE, garage_notch,
            [door(0, 0.5, 16.0), door(1, 0.9)], T, "garage with a 4x6 stair landing notched from one corner"),
        env("t2_pbath_U", RoomType.PRIMARY_BATH, u_shape,
            [door(0, 0.2), window(2, 0.5, 2.5)], T, "U-shaped primary bath wrapping a linen closet"),
        env("t2_sbath_chase", RoomType.SECONDARY_BATH, chase,
            [door(0, 0.5), window(2, 0.5, 2.0)], T, "5x9 bath with a 2x2 duct chase in a corner"),
        env("t2_sbed_chimney", RoomType.SECONDARY_BEDROOM, chimney,
            [door(7, 0.15), window(0, 0.5, 3.0), window(4, 0.5, 2.5)], T,
            "bedroom with a chimney breast intruding mid-wall"),
    ]
