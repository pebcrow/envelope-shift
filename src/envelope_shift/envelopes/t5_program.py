"""T5: unconventional program. Valid rooms whose function departs from the
standard type. These are the rooms that expose the coverage penalty, and the
ones E2 hand-authors paired layouts for.

Each envelope carries two things, and they must never be merged again:

  brief                the program, in a sentence. TRANSMITTED to the model; it is the only
                       way a T5 room's atypicality (which is programmatic, not geometric)
                       reaches it. It must not name a declared-extraneous type as a token.
  declared_extraneous  the desirable entity types that inventory.py scores as extraneous for
                       the room type. The scorer's answer key: HELD OUT of every prompt, used
                       by scoring and by the E2 pairs. The test in tests/test_tiers_t45.py
                       checks each named type is genuinely outside the type's expected
                       inventory, and tests/test_prompt_brief.py that none reaches a prompt.
"""

from ..schema import RoomType, Tier
from ._helpers import door, env, rect, window

T = Tier.T5_PROGRAM


def build():
    return [
        env("t5_kitchen_laundry", RoomType.KITCHEN, rect(14, 18),
            [door(0, 0.15), door(3, 0.85), window(2, 0.5, 5.0)], T,
            "kitchen with an integrated laundry: the laundry program shares the room with the "
            "kitchen",
            declared_extraneous=("washer", "dryer")),
        env("t5_sbed_worknook", RoomType.SECONDARY_BEDROOM, rect(12, 15),
            [door(0, 0.2), window(2, 0.3, 3.0), window(2, 0.7, 3.0)], T,
            "bedroom with a built-in work alcove: the work zone is built-in casework rather "
            "than a loose desk",
            declared_extraneous=("built_in_desk", "built_in_shelving", "window_seat")),
        env("t5_pbath_aging_in_place", RoomType.PRIMARY_BATH, rect(11, 13),
            [door(0, 0.2, width=3.0), window(2, 0.5, 2.5)], T,
            "aging-in-place bath: curbless roll-in shower, 5 ft turning radius, grab bars, "
            "bench",
            declared_extraneous=("roll_in_shower", "grab_bar", "shower_bench")),
        env("t5_pbed_nursery", RoomType.PRIMARY_BEDROOM, rect(15, 17),
            [door(0, 0.15), window(2, 0.25, 3.0), window(2, 0.75, 3.0)], T,
            "primary bedroom with a nursery corner: an infant sleeping and changing zone "
            "shares the room with the bed",
            declared_extraneous=("crib", "changing_table", "glider")),
        env("t5_office_murphy", RoomType.OFFICE, rect(11, 12),
            [door(0, 0.2), window(2, 0.5, 3.0)], T,
            "office doubling as a guest room: a wall bed folds down over the desk zone and needs "
            "its full swing clear",
            declared_extraneous=("murphy_bed",)),
        env("t5_pbath_sauna", RoomType.PRIMARY_BATH, rect(12, 14),
            [door(0, 0.2), window(2, 0.5, 2.5)], T,
            "spa primary bath with a dry-heat cabin beside the shower",
            declared_extraneous=("sauna",)),
        env("t5_garage_workshop", RoomType.GARAGE, rect(24, 26),
            [door(0, 0.5, width=16.0), door(2, 0.1)], T,
            "garage with a dedicated workshop bay: a workbench, stationary tools and dust "
            "collection",
            declared_extraneous=("table_saw", "dust_collector", "tool_chest")),
        env("t5_sbath_laundry_closet", RoomType.SECONDARY_BATH, rect(8, 11),
            [door(0, 0.25), window(2, 0.5, 2.0)], T,
            "secondary bath with a stacked laundry closet on the back wall",
            declared_extraneous=("washer", "dryer")),
    ]
