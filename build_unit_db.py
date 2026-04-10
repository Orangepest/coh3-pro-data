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


SKIP_SBPS = {
    # === Upgrade-disguised-as-unit ===
    "hmg_50cal_us",            # M2HB .50cal - upgrade for M1919 via Heavy Weapons BG
    "halftrack_assault_us",    # M3 Assault Carrier - upgrade via Heavy Weapons BG
    "halftrack_stummel_ger",   # Stummel - upgrade for 251
    "halftrack_stummel_recrewable_ger",
    "armored_car_8_rad_stummel_ak",  # DAK 8 Rad stummel - upgrade variant

    # === Not in multiplayer (campaign / SP only) ===
    "ambulance_us",                    # WC54 Ambulance
    "marksman_team_partisan",          # Marksmen Team
    "medic_us", "medic_partisan",      # Medic squad
    "logistics_truck_us",              # Logistics Truck
    "medic_ger",
    "medic_ak",
    "medic_uk", "medic_africa_uk",
    "sniper_uk", "sniper_africa_uk",   # No British sniper
    "anzioannie_ger",                  # Anzio Annie - campaign superheavy
    "at_gun_88mm_pak43_ger",           # Pak 43 - campaign
    "fallschirmsniper_ger",            # Campaign sniper
    "officer_ger_sp",                  # SP officer
    "logistics_officer_ger",
    "spotter_ger",                     # SP unit

    # === Campaign-only "Command" variants ===
    "armored_car_222_ak",                  # 222 Armored Car (campaign variant)
    "armored_car_8_rad_command_ak",        # Command 8 Rad
    "m13_40_command_ak",                   # Command M13/40
    "panzer_i_command_ak",                 # Command Panzer I
    "panzer_iii_command_ak",               # Command Panzer III
    "panzer_iii_37mm_ak",                  # Panzer III 37mm campaign variant
    "panzer_iii_g_ak", "panzer_iii_n_ak",  # Panzer III G/N variants
    "panzer_iv_f_ak",                      # Panzer IV F variant
    "panzer_iv_sdkfz_161_ak",              # Panzer IV variant
    "panzerjager_i_ak",                    # Panzerjäger I campaign TD
    "bison_ak",                            # Bison Sturmpanzer campaign
    "l6_40_flame_ak",                      # L6/40 Flame Tank campaign
    "nashorn_ger",                         # Nashorn Heavy TD (campaign)
    "command_churchill_uk", "command_churchill_africa_uk",
    "churchill_75mm_uk", "churchill_75mm_africa_uk",  # NA 75 = campaign
    "matilda_command_uk", "matilda_africa_command_uk",
    "valentine_command_uk", "valentine_command_africa_uk",
    "crusader_57mm_uk", "crusader_57mm_africa_uk",  # Crusader III = campaign
    "marmon_herrington_uk", "marmon_herrington_africa_uk",
    "cwt_lrdg_truck_2pdr_africa_uk",
    "cwt_lrdg_truck_africa_uk_uk",
    "halftrack_command_us",                # US command halftrack

    # === Doctrinal-only that need to be filtered from base lists ===
    # These ARE in the multiplayer game but NOT in base roster.
    # We don't skip them entirely (they may show in cohdb data) - we skip them
    # from APPEARING in the base section of our listing only.
    # Use the FORCE_DOCTRINAL_SBPS mechanism for those.

    # === UK doctrinal infantry (all commandos/elite are BG-only) ===
    "commando_uk", "commando_africa_uk",
    "commando_lmg_uk", "commando_lmg_africa_uk",
    "hmg_commando_uk", "hmg_commando_africa_uk",
    "sas_squad_uk", "sas_africa_uk",
    "ssb_commando",
    "guards_uk", "guards_africa_uk",
    "australian_light_infantry_uk",
    "canadian_heavy_infantry_uk",
    "gurkhas_uk",

    # === Italian units that bleed into Wehrmacht race in sbps ===
    # These are DAK Italian-themed units, but cohstats also files them under "german"
    "bersaglieri_ger", "guastatori_ger",
    "coastal_reserves_ger", "coastal_reserves_at_ger",
    "fallschirmjagers_ger", "fallschirmpioneers_ger",
    "kriegsmarine_infantry_ak",  # Kriegsmarine BG only
    "kriegsmariner_ger",
    "m13_40_ger",                # Carro Armato in wehr - shouldn't be there
    "l6_40_ger",                 # L6/40 in wehr - shouldn't be there
    "l6_40_recrewable_ger",
    "borgward_iv_ger",           # Last Stand BG only
    "halftrack_recrewable_ger",  # 251 recrewable variant
    "recovery_vehicle_ger",      # 18-tonne recovery vehicle - campaign
    # Note: kettenkrad_ger and armored_car_ger ARE valid Wehr base units (T0 / 221 Scout Car)
    # Note: guards_uk / guards_africa_uk ARE valid UK T4 base (Foot Guards)

    # === Aircraft entities (not playable squads) ===
    "b25j_bomber_us", "c47_douglas_us",
    "p47_thunderbolt_dive_bomber_us", "p47_thunderbolt_us",
    "l2_grasshopper_recon_reveal_fow_us",
    "l2_grasshopper_recon_reveal_los_high_altitude_us",
    "l2_grasshopper_recon_reveal_los_us",

    # === Partisan callins (these are US Partisans BG) ===
    "resistance_fighters_battlegroup_partisans",
    "resistance_fighters_partisan",
    "saboteurs_battlegroup_partisan",
    "saboteurs_partisan",

    # === Trucks/medical/utility variants - filter the SP duplicates ===
    "truck_4x4_medical_us",
    "halftrack_medical_us",
    "halftrack_medical_ger", "halftrack_250_medical_ak", "halftrack_medical_ak",
    "halftrack_250_mortar_ak",     # Mortar Half-track
    "halftrack_251_weapon_supply_ak",  # Supply Half-track
    "halftrack_251_flak_ger",          # Flak Half-track
    "truck_2_5_medical_ger", "truck_2_5_medical_ak",
    "truck_2_5_towed_cannone_da_105_ak",
    "cwt_15_truck_medical_uk", "cwt_15_truck_medical_africa_uk",
    "cwt_15_truck_repair_resupply_uk", "cwt_15_truck_repair_resupply_africa_uk",
    "cwt_15_quad_mount_uk", "cwt_15_quad_mount_africa_uk",
    "cwt_15_flatbed_uk", "cwt_15_flatbed_africa_uk",
    "cwt_15_truck_uk", "cwt_15_truck_africa_uk", "cwt_15_truck_recrewable_africa_uk",
    "cwt_15_truck_uk",
    "australian_supplytruck_africa_uk",
}


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
                if sbps_id in SKIP_SBPS:
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


# Patterns in ability ids that indicate "this ability unlocks base production"
# rather than (or in addition to) spawning a one-time call-in.
DUAL_AVAILABILITY_PATTERNS = [
    "production_unlock",   # explicit production unlock
    "passive",             # passive unlock (e.g. .50cal hmg)
    "assault_group",       # spawn + unlock production (Stoßtruppen, StuG III D)
    "convert",             # convert existing unit (Rangers, Sturmpioneers)
    "_package",            # mechanized_right_3a_stosstruppen_package etc
]

# Specific ability ids that are dual-availability but don't match the patterns above
DUAL_AVAILABILITY_EXPLICIT = {
    "last_stand_sturmpioneers_ger",
    "polish_cavalry_sherman_firefly_uk",
}


def is_dual_availability_ability(ability_id: str) -> bool:
    aid = ability_id.lower()
    if ability_id in DUAL_AVAILABILITY_EXPLICIT:
        return True
    return any(p in aid for p in DUAL_AVAILABILITY_PATTERNS)


# Hand-curated dual-availability mappings.
# These are units where the BG ability unlocks base production rather than
# (or in addition to) spawning a one-time call-in. The workarounds.ts file
# from coh3-stats is stale relative to the live game data, so we maintain
# these manually based on the BG upgrade ids in battlegroup.json.
EXTRA_BG_LINKAGES = {
    # ability_id -> list of sbps_ids it unlocks/spawns
    # ----- USF -----
    "armored_right_3_sherman_easy_8_production_unlock_us": ["sherman_easy_8_us"],
    "infantry_left_1_convert_rifleman_to_ranger_us": ["ranger_us"],
    "infantry_right_1a_artillery_observers_us": ["artillery_observers_us"],
    "infantry_right_2_howitzer_105mm_us": ["howitzer_105mm_us"],
    "special_operations_sherman_whizbang_production_unlock_us": ["sherman_whizbang_us"],
    "special_weapons_pershing_us": ["pershing_us"],
    "special_weapons_at_gun_3in_m5_us": ["at_gun_3in_m5_us"],
    # ----- UK -----
    "british_armored_churchill_production_unlock_uk": ["churchill_uk", "churchill_africa_uk"],
    # ----- Wehr -----
    "mechanized_left_panther_production_unlock_ger": ["panther_ger"],
    "mechanized_left_2a_stug_assault_group": ["stug_iii_d_ger"],
    "mechanized_left_2b_8_rad": ["armored_car_8_rad_ger"],  # Wehr 8 Rad is BG-only
    "mechanized_right_3a_stosstruppen_package": ["stormtrooper_ger"],
    "last_stand_sturmpioneers_ger": ["sturmpioneer_ger"],
    # Sherman Firefly via UK Polish Cavalry
    "polish_cavalry_sherman_firefly_uk": ["sherman_firefly_africa_uk", "sherman_firefly_uk"],
}

# Buildings/upgrades that are battlegroup-locked, not base.
# These are NOT in sbps - they're in ebps (buildings.json) or are pure upgrades.
# Map: building_or_upgrade_name -> battlegroup_id (and faction)
BG_LOCKED_BUILDINGS = {
    # USF
    "Frontline Medical Station": ("infantry", "us"),  # Advanced Infantry BG
    # UK heavy artillery emplacements (all doctrinal except Bishop)
    "BL5.5 Artillery Emplacement": ("indian_artillery", "uk"),
    "B.L. 5.5-Inch Artillery Emplacement": ("indian_artillery", "uk"),
    "25-pounder Artillery Emplacement": ("indian_artillery", "uk"),
    "17-pounder Anti-tank Emplacement": ("british_armored", "uk"),
    # Wehr/DAK
    "leFH 18 Howitzer Emplacement": ("italian_coastal", "wehr"),
}

# sbps_ids of units that should be marked as doctrinal/call-in even when
# the SpawnItemMappings doesn't catch them. Used for units we know are BG-locked
# from manual game knowledge but where the BG ability id linkage is missing.
FORCE_DOCTRINAL_SBPS = {
    # Heavy artillery / howitzer units (all doctrinal except UK Bishop)
    "wespe_ger": "mechanized",                 # Wespe SPG - Wehr Mechanized BG
    "scott_us": "armored",                     # M8 Scott SPG - already detected but for safety
    "howitzer_25pdr_uk": None,                 # 25-pdr emplacement - doctrinal
    "howitzer_25pdr_africa_uk": None,
    "howitzer_base_25pdr_uk": None,
    "howitzer_base_25pdr_africa_uk": None,
    "howitzer_bl_5_5_uk": "indian_artillery",
    "mortar_heavy_4_2_uk": "indian_artillery",
    "mortar_heavy_4_2_africa_uk": "indian_artillery",
    "pack_howitzer_75mm_uk": "british_air_and_sea",
    "howitzer_105mm_ger": "italian_coastal",   # leFH 18
    "howitzer_cannone_da_105_ger": "italian_coastal",
}

# Upgrades that LOOK like units in cohdb but are pure upgrades, not call-ins.
# These should NEVER be classified as production.
KNOWN_UPGRADES = {
    "M2HB .50cal Heavy Machine Gun",  # special_weapons_50cal_mg_us upgrade
    "Assault Carriers",                # special_weapons_assault_halftrack_m3_us upgrade
}


def build_canonical_lookup():
    """Build sbps_id -> (faction, tier, locked) lookup from canonical roster."""
    from canonical_roster import CANONICAL_BASE
    lookup = {}
    for faction, tiers in CANONICAL_BASE.items():
        for tier, units in tiers.items():
            for u in units:
                lookup[u["sbps_id"]] = {
                    "faction": faction,
                    "tier": tier,
                    "tier_upgrade_locked": u.get("tier_upgrade_locked", False),
                }
    return lookup


def build_unit_db():
    print("Loading locstring...")
    locstring = load_locstring()

    print("Parsing battlegroups...")
    bgs = parse_battlegroups()
    print(f"  Found {len(bgs)} battlegroups")

    print("Parsing SpawnItemMappings...")
    spawn = parse_spawn_mappings()
    print(f"  Found {len(spawn)} call-in mappings from workarounds.ts")

    # Merge in our hand-curated extras (workarounds.ts is often stale)
    for ability_id, sbps_ids in EXTRA_BG_LINKAGES.items():
        if ability_id not in spawn:
            spawn[ability_id] = sbps_ids
    print(f"  After extras: {len(spawn)} mappings")

    # Build sbps_id -> (bg_id, faction, ability_id, is_dual)
    sbps_to_bg = {}
    for bg_id, bg_info in bgs.items():
        for upg_id in bg_info["upgrade_ids"]:
            for sbps_id in spawn.get(upg_id, []):
                dual = is_dual_availability_ability(upg_id)
                sbps_to_bg[sbps_id] = {
                    "bg_id": bg_id,
                    "bg_faction": bg_info["faction"],
                    "ability_id": upg_id,
                    "dual_availability": dual,
                }

    print("Parsing sbps (squads)...")
    squads = parse_sbps(locstring)
    print(f"  Found {len(squads)} squads")

    # Build canonical roster lookup
    canonical = build_canonical_lookup()
    print(f"  Canonical roster has {len(canonical)} base units")

    # Annotate with BG info
    for sq in squads:
        # Canonical roster info
        canon = canonical.get(sq["sbps_id"])
        if canon:
            sq["is_canonical_base"] = True
            sq["tier"] = canon["tier"]
            sq["tier_upgrade_locked"] = canon["tier_upgrade_locked"]
        else:
            sq["is_canonical_base"] = False
            sq["tier"] = None
            sq["tier_upgrade_locked"] = False

        link = sbps_to_bg.get(sq["sbps_id"])
        if link:
            sq["is_callin"] = True
            sq["battlegroup"] = link["bg_id"]
            # True dual = canonical base AND has a BG callin (e.g. Stoßtruppen, 251)
            # NOT dual = BG production unlock for a non-base unit (e.g. Easy Eight, Whizbang)
            sq["dual_availability"] = sq["is_canonical_base"] and link is not None
            # Track BG-unlocks-base-production separately
            sq["bg_unlocks_production"] = link["dual_availability"] and not sq["is_canonical_base"]
            sq["unlocking_ability"] = link["ability_id"]
        elif sq["sbps_id"] in FORCE_DOCTRINAL_SBPS:
            sq["is_callin"] = True
            sq["battlegroup"] = FORCE_DOCTRINAL_SBPS[sq["sbps_id"]]
            sq["dual_availability"] = False
            sq["bg_unlocks_production"] = False
            sq["unlocking_ability"] = "manual_override"
        else:
            sq["is_callin"] = False
            sq["battlegroup"] = None
            sq["dual_availability"] = False
            sq["bg_unlocks_production"] = False
            sq["unlocking_ability"] = None

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
