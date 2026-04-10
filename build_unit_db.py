"""
Build an authoritative unit database from cohstats game data.

Outputs game_data/unit_db.json with one entry per squad:
{
  "sbps_id": "riflemen_us",
  "name": "Riflemen Squad",
  "faction": "us",
  "role": "infantry",
  "squad_types": [...],
  "is_callin": False,
  "battlegroup": None
}
"""

import json
import re
from pathlib import Path

GAME_DATA = Path(__file__).parent / "game_data"

# Map raw race ids to short faction names used in our project
FACTION_MAP = {
    "american": "us",
    "german": "wehr",
    "british": "uk",
    "british_africa": "uk",
    "afrika_korps": "dak",
}

# Map raw race ids to readable battlegroup faction names
BG_FACTION = {
    "afrika_korps": "dak",
    "american": "us",
    "british": "uk",
    "german": "wehr",
}


def load_locstring():
    with open(GAME_DATA / "locstring.json") as f:
        return json.load(f)


def parse_spawn_mappings():
    """Parse SpawnItemMappings from workarounds.ts -> dict[ability_id, list[sbps_ids]]."""
    text = (GAME_DATA / "workarounds.ts").read_text()
    # Find the SpawnItemMappings object
    m = re.search(
        r"const SpawnItemMappings:[^=]*=\s*\{([^}]*?)};",
        text, re.DOTALL,
    )
    if not m:
        # Try non-greedy across blocks
        m = re.search(
            r"const SpawnItemMappings:[^=]*=\s*\{(.*?)\n};",
            text, re.DOTALL,
        )
    if not m:
        raise RuntimeError("SpawnItemMappings not found")

    body = m.group(1)
    mappings = {}
    # Handle both single-line and multi-line entries
    # Pattern: ability_id: ["squad1", "squad2", ...]
    entry_re = re.compile(
        r'([a-zA-Z0-9_]+)\s*:\s*\[\s*((?:"[^"]+"\s*,?\s*)+)\s*\]',
        re.DOTALL,
    )
    for em in entry_re.finditer(body):
        ability_id = em.group(1)
        squads = re.findall(r'"([^"]+)"', em.group(2))
        mappings[ability_id] = squads
    return mappings


def parse_battlegroups():
    """Parse battlegroup.json -> dict[bg_id, {faction, name_locstring, upgrade_ids}]."""
    with open(GAME_DATA / "battlegroup.json") as f:
        data = json.load(f)

    bgs = {}
    for race_key, bg_dict in data.get("races", {}).items():
        faction = BG_FACTION.get(race_key, race_key)
        for bg_id, bg_data in bg_dict.items():
            techtree = bg_data.get("techtree_bag", {})
            name_loc = techtree.get("name", {}).get("locstring", {}).get("value")
            upgrade_ids = []
            for branch_wrapper in techtree.get("branches", []):
                branch = branch_wrapper.get("branch", {})
                for upg_wrapper in branch.get("upgrades", []):
                    ref = upg_wrapper.get("upgrade", {}).get("instance_reference", "")
                    if ref:
                        upgrade_ids.append(ref.split("/")[-1])
            bgs[bg_id] = {
                "faction": faction,
                "name_locstring": name_loc,
                "upgrade_ids": upgrade_ids,
            }
    return bgs


def parse_sbps(locstring):
    """Parse sbps.json -> list of squad dicts."""
    with open(GAME_DATA / "sbps.json") as f:
        data = json.load(f)

    squads = []
    for race_key, role_dict in data.get("races", {}).items():
        if race_key == "common":
            continue
        faction = FACTION_MAP.get(race_key, race_key)
        for role, squads_dict in role_dict.items():
            if not isinstance(squads_dict, dict):
                continue
            for sbps_id, sq in squads_dict.items():
                if not isinstance(sq, dict):
                    continue
                # Find UI extension for screen_name
                screen_name_loc = None
                squad_types = []
                for ext in sq.get("extensions", []):
                    if not isinstance(ext, dict):
                        continue
                    sqe = ext.get("squadexts", {})
                    tref = sqe.get("template_reference", {}).get("value", "")
                    if "ui_ext" in tref:
                        try:
                            info = sqe.get("race_list", [{}])[0].get("race_data", {}).get("info", {})
                            screen_name_loc = info.get("screen_name", {}).get("locstring", {}).get("value")
                        except Exception:
                            pass
                    elif "squad_type_ext" in tref:
                        for st in sqe.get("squad_type_list", []):
                            t = st.get("squad_type") if isinstance(st, dict) else None
                            if t:
                                squad_types.append(t)

                name = locstring.get(screen_name_loc, sbps_id) if screen_name_loc else sbps_id
                squads.append({
                    "sbps_id": sbps_id,
                    "name": name,
                    "faction": faction,
                    "race_key": race_key,
                    "role": role,
                    "squad_types": squad_types,
                })
    return squads


def build_unit_db():
    print("Loading locstring...")
    locstring = load_locstring()

    print("Parsing battlegroups...")
    bgs = parse_battlegroups()
    print(f"  Found {len(bgs)} battlegroups")

    print("Parsing SpawnItemMappings...")
    spawn = parse_spawn_mappings()
    print(f"  Found {len(spawn)} call-in mappings")

    # Build sbps_id -> battlegroup_id reverse map
    sbps_to_bg = {}
    for bg_id, bg_info in bgs.items():
        for upg_id in bg_info["upgrade_ids"]:
            for sbps_id in spawn.get(upg_id, []):
                sbps_to_bg[sbps_id] = (bg_id, bg_info["faction"])

    print("Parsing sbps (squads)...")
    squads = parse_sbps(locstring)
    print(f"  Found {len(squads)} squads")

    # Annotate with BG info
    for sq in squads:
        bg_info = sbps_to_bg.get(sq["sbps_id"])
        if bg_info:
            sq["is_callin"] = True
            sq["battlegroup"] = bg_info[0]
        else:
            sq["is_callin"] = False
            sq["battlegroup"] = None

    # Resolve battlegroup display names
    for bg_id, bg_info in bgs.items():
        bg_info["display_name"] = locstring.get(bg_info["name_locstring"], bg_id)

    # Save outputs
    out = {
        "squads": squads,
        "battlegroups": bgs,
    }
    out_path = GAME_DATA / "unit_db.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path}")
    print(f"  {len(squads)} squads")
    callins = sum(1 for s in squads if s["is_callin"])
    print(f"  {callins} call-in (battlegroup-locked)")
    print(f"  {len(squads) - callins} base tech-tree")
    return out


if __name__ == "__main__":
    build_unit_db()
