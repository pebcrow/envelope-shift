"""T0: rectangular, typical proportions, standard production sizes.

This tier validates the harness against the published numbers. It proves
nothing on its own.
"""

from ..schema import RoomType, Tier
from ._helpers import door, env, rect, window

T = Tier.T0_CALIBRATION


def build():
    return [
        env("t0_kitchen_12x14", RoomType.KITCHEN, rect(12, 14),
            [door(3, 0.2), window(2, 0.5, 4.0)], T, "typical galley-plus kitchen"),
        env("t0_kitchen_14x16", RoomType.KITCHEN, rect(14, 16),
            [door(0, 0.15), door(1, 0.8), window(2, 0.5, 5.0)], T, "typical open kitchen, two entries"),
        env("t0_pbath_10x12", RoomType.PRIMARY_BATH, rect(10, 12),
            [door(0, 0.2), window(2, 0.5, 2.5)], T, "typical primary bath"),
        env("t0_sbath_5x9", RoomType.SECONDARY_BATH, rect(5, 9),
            [door(0, 0.5)], T, "typical 5x9 hall bath"),
        env("t0_pbed_14x16", RoomType.PRIMARY_BEDROOM, rect(14, 16),
            [door(0, 0.15), window(2, 0.35, 3.0), window(2, 0.65, 3.0)], T, "typical primary bedroom"),
        env("t0_sbed_11x12", RoomType.SECONDARY_BEDROOM, rect(11, 12),
            [door(0, 0.2), window(2, 0.5, 3.0)], T, "typical secondary bedroom"),
        env("t0_sbed_12x12", RoomType.SECONDARY_BEDROOM, rect(12, 12),
            [door(3, 0.8), window(1, 0.5, 3.0)], T, "typical square secondary bedroom"),
        env("t0_office_10x11", RoomType.OFFICE, rect(10, 11),
            [door(0, 0.2), window(2, 0.5, 3.0)], T, "typical front-of-house office"),
    ]
