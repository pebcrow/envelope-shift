"""T3: non-orthogonal walls. 30- and 45-degree walls, trapezoids, chamfers,
and two curved walls approximated as fine polylines.

Every room here has at least one wall that is not parallel to an axis
(tests/test_tiers_t23.py enforces this). Openings sit only on straight walls
long enough to hold them. All vertex lists are CCW.
"""

import math

from ..schema import RoomType, Tier
from ._helpers import door, env, window

T = Tier.T3_NONORTHOGONAL


def _curved_wall(cx, cy, r, a0, a1, n=12):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in [a0 + (a1 - a0) * k / n for k in range(1, n)]]


def _p(x, y):
    """Round a computed vertex so the dumped JSON stays readable."""
    return (round(x, 4), round(y, 4))


def build():
    # 45-degree chamfered corner on a 14x16 bedroom.
    chamfer = [(0, 0), (14, 0), (14, 12), (10, 16), (0, 16)]
    # Trapezoid office: front wall 10 ft, back wall 14 ft.
    trapezoid = [(2, 0), (12, 0), (14, 11), (0, 11)]
    # Bath with one bowed wall (arc of radius 12 bulging outward on the right).
    bowed = [(0, 0), (10, 0)] + _curved_wall(-2, 6, 12, -30, 30)[::1] + [(10, 12), (0, 12)]
    # 14x12 kitchen whose top-right corner is cut by a 6 ft wall at 30 degrees
    # (rise 3 over run 3*sqrt(3)). Wall 1 is the right wall, wall 2 the
    # angled wall, wall 3 the remaining top wall, wall 4 the left wall.
    kitchen_30 = [(0, 0), (14, 0), (14, 9), _p(14 - 3 * math.sqrt(3), 12), (0, 12)]
    # 12x13 secondary bedroom with a 45-degree bay projecting 2 ft from the
    # top wall: sides on walls 3 and 5 (2*sqrt(2) long), 4 ft front on wall 4.
    bay = [(0, 0), (12, 0), (12, 13), (10, 13), (8, 15), (4, 15), (2, 13), (0, 13)]
    # Tapered garage on a wedge lot: 24 ft front, 20 ft back, right wall
    # leans in over 22 ft of depth.
    garage_taper = [(0, 0), (24, 0), (20, 22), (0, 22)]
    # 6 ft wide secondary bath with a half-round far end: a 180-degree arc of
    # radius 3 centred on (3, 8), as a 12-segment polyline (~0.79 ft each).
    halfround = [(0, 0), (6, 0), (6, 8)] + [_p(*v) for v in _curved_wall(3, 8, 3, 0, 180)] + [(0, 8)]
    # 16x16 primary bedroom with 4 ft chamfers on all four corners: an octagon
    # with 8 ft axis walls (0, 2, 4, 6) and 4*sqrt(2) ft chamfers (1, 3, 5, 7).
    octagon = [(4, 0), (12, 0), (16, 4), (16, 12), (12, 16), (4, 16), (0, 12), (0, 4)]
    return [
        env("t3_pbed_chamfer", RoomType.PRIMARY_BEDROOM, chamfer,
            [door(0, 0.15), window(3, 0.5, 3.0)], T, "45-degree chamfered corner"),
        env("t3_office_trapezoid", RoomType.OFFICE, trapezoid,
            [door(0, 0.3), window(2, 0.5, 3.0)], T, "trapezoidal office"),
        env("t3_pbath_bowed", RoomType.PRIMARY_BATH, bowed,
            [door(0, 0.2)], T, "one curved wall as a 12-segment polyline"),
        env("t3_kitchen_30deg", RoomType.KITCHEN, kitchen_30,
            [door(4, 0.15), window(2, 0.5, 3.0), window(1, 0.5, 3.0)], T,
            "kitchen with one corner cut by a 30-degree wall"),
        env("t3_sbed_bay45", RoomType.SECONDARY_BEDROOM, bay,
            [door(0, 0.2), window(4, 0.5, 3.0), window(3, 0.5, 2.0), window(5, 0.5, 2.0)], T,
            "bedroom with a 45-degree bay window projecting 2 ft"),
        env("t3_garage_taper", RoomType.GARAGE, garage_taper,
            [door(0, 0.5, 16.0), door(3, 0.85)], T, "tapered garage on a wedge lot, one leaning wall"),
        env("t3_sbath_halfround", RoomType.SECONDARY_BATH, halfround,
            [door(0, 0.5), window(1, 0.7, 2.0)], T, "half-round end wall as a 12-segment polyline"),
        env("t3_pbed_octagon", RoomType.PRIMARY_BEDROOM, octagon,
            [door(6, 0.3), window(2, 0.5, 4.0), window(1, 0.5, 3.0), window(3, 0.5, 3.0)], T,
            "octagonal turret bedroom, four 45-degree chamfers"),
    ]
