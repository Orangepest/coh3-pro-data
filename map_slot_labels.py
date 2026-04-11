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

    # === To be labeled (need slot↔position mapping confirmed) ===
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


# User observations from Propagandacast videos. These are physical positions
# of specific players in specific cast games, but we don't yet know which slot
# (0 or 1) those players occupied in those casts (the cast .rec files aren't
# in our DB). To convert these to slot labels we need:
#   1. The user's gut feel for which side is favored on each map, OR
#   2. The cast .rec files added to our DB
USER_OBSERVATIONS = {
    "bologna_2p":          {"player": "Reakly",     "faction": "uk",   "position": "south", "video": "CBGDw9mzn7s"},
    "djebel_2p":           {"player": "Nub",        "faction": "uk",   "position": "right", "video": "mIYZB63v7NE"},
    "langres_2p":          {"player": "Rei",        "faction": "wehr", "position": "south", "video": "2_ZtvimPb0w"},
    "angoville_farms_2p":  {"player": "Tushkan",    "faction": "wehr", "position": "south", "video": "PUtUsnQP4Ac"},
    "twin_beach_2p_mkii":  {"player": "Barbarossa", "faction": "us",   "position": "south", "video": "HVFPW50gqrQ"},
    "faymonville":         {"player": "Rei",        "faction": "dak",  "position": "north", "video": "PKvfTqQp2HU"},
    "pachino_2p":          {"player": "RedxWings",  "faction": "us",   "position": "right", "video": "0a-6RarGRv0"},
    "villa_fiore_2p_mkii": {"player": "FeriG",      "faction": "dak",  "position": "south", "video": "09m472rCano"},
}


def slot_label(map_name: str, slot: int) -> str:
    """Return the physical position label for (map, slot), or 'slot N' if unknown."""
    if map_name in MAP_SLOT_LABELS and slot in MAP_SLOT_LABELS[map_name]:
        return MAP_SLOT_LABELS[map_name][slot]
    return f"slot {slot}"


def is_labeled(map_name: str) -> bool:
    return map_name in MAP_SLOT_LABELS and len(MAP_SLOT_LABELS[map_name]) >= 2
