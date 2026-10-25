"""T1: proportion and scale. Long/narrow, ADU-scale, unusual ceiling heights.

Every room here is still a rectangle with orthogonal walls; only its aspect
ratio, absolute size, or ceiling height is off the production norm. Two rooms
(t1_pbed_14x16_low, t1_kitchen_12x14_tall) reuse a T0 footprint exactly so the
ceiling change is the only variable.
"""

from ..schema import Ceiling, RoomType, Tier
from ._helpers import door, env, rect, window

T = Tier.T1_PROPORTION


def build():
    return [
        env("t1_pbed_9x22", RoomType.PRIMARY_BEDROOM, rect(9, 22),
            [door(0, 0.5), window(1, 0.5, 3.0)], T, "long narrow bedroom, 9 ft wide"),
        env("t1_kitchen_7x16_adu", RoomType.KITCHEN, rect(7, 16),
            [door(3, 0.1), window(2, 0.5, 3.0)], T, "ADU galley kitchen, 7 ft wide"),
        env("t1_office_7x8", RoomType.OFFICE, rect(7, 8),
            [door(0, 0.5)], T, "closet-sized office, no window"),
        env("t1_pbed_14x16_low", RoomType.PRIMARY_BEDROOM, rect(14, 16),
            [door(0, 0.15), window(2, 0.5, 3.0)], T, "typical plan, 7 ft ceiling",
            ceiling=Ceiling(height=7.0)),
        env("t1_sbath_4x11", RoomType.SECONDARY_BATH, rect(4, 11),
            [door(0, 0.5)], T, "long narrow hall bath, 4 ft wide"),
        env("t1_sbed_8x10_adu", RoomType.SECONDARY_BEDROOM, rect(8, 10),
            [door(0, 0.2), window(2, 0.5, 3.0)], T, "ADU-scale bedroom, 80 sq ft near code minimum"),
        env("t1_pbath_6x18", RoomType.PRIMARY_BATH, rect(6, 18),
            [door(3, 0.5), window(2, 0.5, 2.5)], T, "long narrow primary bath, 6 ft wide at 3:1"),
        env("t1_kitchen_12x14_tall", RoomType.KITCHEN, rect(12, 14),
            [door(3, 0.2), window(2, 0.5, 4.0)], T, "typical plan, 13 ft loft ceiling",
            ceiling=Ceiling(height=13.0)),
    ]
