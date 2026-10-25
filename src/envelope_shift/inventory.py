"""Expected inventory per room type, with alternative groups.

The published coverage metric scores a layout against "an expected inventory
for the room type" with alternative groups (bathtub *or* shower). The tables
themselves are not published. These are authored from ordinary US production
practice and are deliberately conservative: they describe what a typical
room contains, which is exactly what makes coverage a conformity measure.

Each inventory line is either:
    Item(type, count)              - required type, required minimum count
    Group(name, alternatives)      - satisfied by any one alternative type

Entities of a type that appears in neither the lines nor `tolerated` are
extraneous and penalized. `targets` are the destinations navigability paths
to; the published post names bed, shower and kitchen counter as examples.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import RoomType


@dataclass(frozen=True)
class Item:
    type: str
    count: int = 1


@dataclass(frozen=True)
class Group:
    name: str
    alternatives: tuple[str, ...]


@dataclass(frozen=True)
class Inventory:
    lines: tuple[Item | Group, ...]
    tolerated: frozenset[str] = field(default_factory=frozenset)
    targets: tuple[str, ...] = ()

    @property
    def n(self) -> int:
        return len(self.lines)

    def expected_types(self) -> set[str]:
        out: set[str] = set()
        for line in self.lines:
            if isinstance(line, Item):
                out.add(line.type)
            else:
                out.update(line.alternatives)
        return out | set(self.tolerated)


INVENTORY: dict[RoomType, Inventory] = {
    # Kitchen, primary bath and secondary bath are sized to production
    # practice (SPEC.md A3): the first T0 run scored coverage 100 on every
    # room because these three tables were thin. Counts are what a typical
    # US production kitchen / bath schedule carries, not a minimum to be
    # habitable. Alternative groups are kept so a layout is not punished for
    # choosing a cooktop + wall oven over a range, or a shower over a tub.
    RoomType.KITCHEN: Inventory(
        lines=(
            # A 12x14 production kitchen runs ~18-20 lf of base cabinet at
            # 30-36 in modules: six boxes is the low end once the sink base,
            # the dishwasher gap and the range gap are taken out.
            Item("base_cabinet", 6),
            # Uppers track the base run minus the range hood and window.
            Item("upper_cabinet", 5),
            Item("sink"),
            Item("refrigerator"),
            # Cooking surface: a freestanding range, or a cooktop with the
            # oven elsewhere. A range satisfies both groups.
            Group("cooking", ("range", "cooktop")),
            Group("oven", ("range", "wall_oven")),
            # Exhaust over the cooking surface; a microwave-hood does both.
            Group("ventilation", ("range_hood", "microwave_hood")),
            Item("dishwasher"),
            Group("microwave", ("microwave", "microwave_hood", "microwave_drawer")),
            # Dry storage: a walk-in, a reach-in, or a tall pantry cabinet.
            Group("pantry", ("pantry", "pantry_cabinet", "tall_cabinet")),
        ),
        tolerated=frozenset({"island", "peninsula", "trash_pullout", "beverage_fridge", "bar_stool"}),
        targets=("sink", "refrigerator", "range", "cooktop"),
    ),
    RoomType.PRIMARY_BATH: Inventory(
        lines=(
            Item("toilet"),
            # A primary bath carries a double vanity or two singles; one
            # double_vanity entity or one vanity entity satisfies the line.
            Group("vanity", ("vanity", "double_vanity")),
            Group("bathing", ("bathtub", "shower_stall")),
            # Nearly every production primary bath has a shower; tub-only
            # loses this line, tub-and-shower satisfies both.
            Group("shower", ("shower_stall", "tub_shower")),
            Group("linen", ("linen_cabinet", "linen_closet")),
            Item("towel_bar"),
            Group("medicine", ("medicine_cabinet", "mirror")),
        ),
        tolerated=frozenset({"hamper", "wall_shelf", "makeup_vanity"}),
        targets=("toilet", "vanity", "double_vanity", "bathtub", "shower_stall"),
    ),
    RoomType.SECONDARY_BATH: Inventory(
        lines=(
            Item("toilet"),
            Item("vanity"),
            Group("bathing", ("bathtub", "shower_stall", "tub_shower")),
            Item("towel_bar"),
            Group("medicine", ("medicine_cabinet", "mirror")),
            # A 5x9 hall bath has no floor for a linen cabinet; shelving over
            # the toilet is the production answer.
            Group("storage", ("linen_cabinet", "wall_shelf", "over_toilet_shelf")),
        ),
        tolerated=frozenset({"hamper"}),
        targets=("toilet", "vanity", "bathtub", "shower_stall", "tub_shower"),
    ),
    RoomType.PRIMARY_BEDROOM: Inventory(
        lines=(
            Group("bed", ("bed_king", "bed_queen")),
            Item("nightstand", 2),
            Item("dresser"),
        ),
        tolerated=frozenset({"chair", "bench", "tv_console", "closet"}),
        targets=("bed_king", "bed_queen", "dresser"),
    ),
    RoomType.SECONDARY_BEDROOM: Inventory(
        lines=(
            Group("bed", ("bed_queen", "bed_full", "bed_twin")),
            Item("nightstand"),
            Item("dresser"),
        ),
        tolerated=frozenset({"desk", "chair", "closet", "bookshelf"}),
        targets=("bed_queen", "bed_full", "bed_twin", "dresser"),
    ),
    RoomType.OFFICE: Inventory(
        lines=(
            Item("desk"),
            Item("office_chair"),
            Item("bookshelf"),
        ),
        tolerated=frozenset({"filing_cabinet", "chair", "credenza", "closet"}),
        targets=("desk",),
    ),
    RoomType.GARAGE: Inventory(
        lines=(
            Item("parking_space", 2),
            Item("water_heater"),
        ),
        tolerated=frozenset({"workbench", "storage_shelf", "hvac_unit"}),
        targets=("parking_space", "water_heater"),
    ),
}


def inventory_for(room_type: RoomType) -> Inventory:
    return INVENTORY[room_type]
