"""
Generate a complete listing of every battlegroup and its abilities/upgrades.
Pulls from battlegroup.json + upgrade.json + locstring.json.
"""

import json
from pathlib import Path

GAME_DATA = Path(__file__).parent / "game_data"


def load_locstring():
    with open(GAME_DATA / "locstring.json") as f:
        return json.load(f)


def load_battlegroups():
    with open(GAME_DATA / "battlegroup.json") as f:
        return json.load(f)


def load_upgrades():
    with open(GAME_DATA / "upgrade.json") as f:
        return json.load(f)


def get_upgrade_name(upgrade_obj, locstring):
    """Extract human-readable name from an upgrade entry."""
    try:
        # Try the upgrade_bag.ui_info.screen_name path
        bag = upgrade_obj.get("upgrade_bag", {})
        ui = bag.get("ui_info", {})
        sn = ui.get("screen_name", {}).get("locstring", {}).get("value")
        if sn and sn != "0":
            name = locstring.get(sn, "")
            if name:
                return name
    except Exception:
        pass
    return None


def index_upgrades(upgrades_data, locstring):
    """Build a dict of upgrade_id -> human readable name."""
    result = {}

    def walk(obj, path=""):
        if isinstance(obj, dict):
            # Look for upgrade entries
            if "upgrade_bag" in obj:
                # The key in the parent is the upgrade id
                pass
            for k, v in obj.items():
                if isinstance(v, dict) and "upgrade_bag" in v:
                    name = get_upgrade_name(v, locstring)
                    if name:
                        result[k] = name
                else:
                    walk(v, path + "/" + str(k))
        elif isinstance(obj, list):
            for item in obj:
                walk(item, path)

    walk(upgrades_data)
    return result


def main():
    locstring = load_locstring()
    bgs = load_battlegroups()
    upgrades = load_upgrades()

    print("Indexing all upgrades...")
    upgrade_names = index_upgrades(upgrades, locstring)
    print(f"  Found {len(upgrade_names)} named upgrades")

    factions = {
        "afrika_korps": "DAK",
        "american": "USF",
        "british": "BRITISH",
        "german": "WEHRMACHT",
    }

    output = []

    for race_key, race_label in factions.items():
        race_bgs = bgs.get("races", {}).get(race_key, {})
        output.append("\n" + "=" * 75)
        output.append(f"  {race_label} BATTLEGROUPS")
        output.append("=" * 75)

        for bg_id, bg_data in race_bgs.items():
            techtree = bg_data.get("techtree_bag", {})
            name_loc = techtree.get("name", {}).get("locstring", {}).get("value")
            bg_name = locstring.get(name_loc, bg_id) if name_loc else bg_id

            output.append(f"\n  >> {bg_name}")
            output.append(f"     (id: {bg_id})")

            for branch_idx, branch_wrapper in enumerate(techtree.get("branches", [])):
                side = "LEFT" if branch_idx == 0 else "RIGHT"
                branch = branch_wrapper.get("branch", {})
                branch_name_loc = branch.get("name", {}).get("locstring", {}).get("value")
                branch_name = locstring.get(branch_name_loc, side) if branch_name_loc else side

                output.append(f"\n     [{side}] {branch_name}")

                for upg_wrapper in branch.get("upgrades", []):
                    ref = upg_wrapper.get("upgrade", {}).get("instance_reference", "")
                    upg_id = ref.split("/")[-1] if ref else "?"
                    name = upgrade_names.get(upg_id, upg_id)
                    output.append(f"       - {name}")

    text = "\n".join(output)
    print(text)

    # Save to file too
    out_file = GAME_DATA / "battlegroup_abilities.txt"
    out_file.write_text(text)
    print(f"\nSaved to {out_file}")


if __name__ == "__main__":
    main()
