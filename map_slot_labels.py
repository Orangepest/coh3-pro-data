"""
Maps slot 0 / slot 1 to physical positions per CoH3 map.

Slot 0 = the player who appears first in the cohdb timeline JSON, which is
slot 0 in the .rec file. This is consistent within a replay but otherwise
random/matchmaking-assigned. By inspecting one casted game per map, we can
label what physical position slot 0 corresponds to on each map.

Format: { map_name: {0: "south position label", 1: "north position label"} }

Empty entries mean we haven't labeled that map yet.
"""

MAP_SLOT_LABELS: dict[str, dict[int, str]] = {
    # Verified by Tushkan vs Nicko Propagandacast game (replay 5270772):
    # Tushkan = slot 0 = south, Nicko = slot 1 = north
    "crossing_in_the_woods_2p": {0: "south", 1: "north"},

    # === To be labeled (need a casted/known game) ===
    # "langres_2p":              {},
    # "twin_beach_2p_mkii":      {},
    # "angoville_farms_2p":      {},
    # "pachino_2p":              {},
    # "bologna_2p":              {},
    # "faymonville":             {},
    # "egletons_2p":             {},
    # "desert_village_2p_mkiii": {},
    # "djebel_2p":               {},
    # "tuscan_vineyard_2p":      {},
    # "cliff_crossing_2p":       {},
    # "villa_fiore_2p_mkii":     {},
}


def slot_label(map_name: str, slot: int) -> str:
    """Return the physical position label for (map, slot), or 'slot N' if unknown."""
    if map_name in MAP_SLOT_LABELS and slot in MAP_SLOT_LABELS[map_name]:
        return MAP_SLOT_LABELS[map_name][slot]
    return f"slot {slot}"


def is_labeled(map_name: str) -> bool:
    return map_name in MAP_SLOT_LABELS and len(MAP_SLOT_LABELS[map_name]) >= 2
