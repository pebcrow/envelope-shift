"""T4: vertical constraint. Sloped ceilings under a roof plane.

The published work names this as not yet modeled, which makes it fair
ground: every model is equally unprepared for it.

Every room here sets a Ceiling with a slope wall, a positive slope, and a
knee-wall minimum, chosen so headroom_at() varies by at least 2 ft across the
floor. Wall indices follow rect(): 0 bottom, 1 right, 2 top, 3 left. The
ceiling is at full height along the slope wall and drops along that wall's
inward normal, so the *opposite* wall is the low side.
"""

from ..schema import Ceiling, RoomType, Tier
from ._helpers import door, env, rect, window

T = Tier.T4_VERTICAL


def build():
    return [
        env("t4_sbed_attic", RoomType.SECONDARY_BEDROOM, rect(12, 14),
            [door(0, 0.2), window(1, 0.5, 3.0)], T,
            "attic bedroom: 8 ft at wall 2, sloping 6:12 to a 4 ft knee wall at wall 0",
            ceiling=Ceiling(height=8.0, slope_wall=2, slope_ft_per_ft=0.5, min_height=4.0)),
        env("t4_office_dormer", RoomType.OFFICE, rect(10, 10),
            [door(3, 0.5), window(1, 0.5, 2.5)], T,
            "dormer office: 8 ft at wall 3, sloping to 5 ft at wall 1",
            ceiling=Ceiling(height=8.0, slope_wall=3, slope_ft_per_ft=0.3, min_height=5.0)),
        env("t4_pbed_attic_gable", RoomType.PRIMARY_BEDROOM, rect(14, 16),
            [door(0, 0.15), window(1, 0.5, 3.0), window(3, 0.5, 3.0)], T,
            "gable attic primary: 9 ft at the ridge wall 2, 6:12 down to a 5 ft knee wall at wall 0; "
            "windows only on the gable ends",
            ceiling=Ceiling(height=9.0, slope_wall=2, slope_ft_per_ft=0.5, min_height=5.0)),
        env("t4_sbed_bonus_over_garage", RoomType.SECONDARY_BEDROOM, rect(20, 12),
            [door(3, 0.5), window(0, 0.3, 3.0), window(0, 0.7, 3.0)], T,
            "bonus room over the garage used as a bedroom: 8 ft at wall 3, 3:12 across 20 ft "
            "to a 4 ft knee wall at wall 1",
            ceiling=Ceiling(height=8.0, slope_wall=3, slope_ft_per_ft=0.25, min_height=4.0)),
        env("t4_sbath_under_roof", RoomType.SECONDARY_BATH, rect(6, 10),
            [door(0, 0.5), window(2, 0.5, 2.0)], T,
            "hall bath tucked under a roof plane: 8 ft at the door wall 0, dropping to a 4.5 ft "
            "knee wall at wall 2; a shower stall fits only on the high side",
            ceiling=Ceiling(height=8.0, slope_wall=0, slope_ft_per_ft=0.4, min_height=4.5)),
        env("t4_pbath_dormer", RoomType.PRIMARY_BATH, rect(10, 12),
            [door(3, 0.2), window(1, 0.5, 2.5)], T,
            "primary bath in a shed dormer: 8.5 ft at wall 3, 6:12 down to 5 ft at the window wall 1",
            ceiling=Ceiling(height=8.5, slope_wall=3, slope_ft_per_ft=0.5, min_height=5.0)),
        env("t4_garage_shed_roof", RoomType.GARAGE, rect(22, 24),
            [door(0, 0.5, width=16.0), door(2, 0.1)], T,
            "shed-roof garage: 10 ft at wall 3 dropping to a 7 ft beam line along wall 1; "
            "tall storage and the water heater flue only clear on the high side",
            ceiling=Ceiling(height=10.0, slope_wall=3, slope_ft_per_ft=0.2, min_height=7.0)),
        env("t4_kitchen_attic_adu", RoomType.KITCHEN, rect(10, 14),
            [door(0, 0.15), window(1, 0.5, 3.0)], T,
            "attic ADU kitchen: 8 ft at wall 1 sloping to a 5 ft knee wall at wall 3; "
            "upper cabinets and the refrigerator only fit against the high wall",
            ceiling=Ceiling(height=8.0, slope_wall=1, slope_ft_per_ft=0.4, min_height=5.0)),
    ]
