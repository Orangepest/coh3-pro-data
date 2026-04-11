"""
Unit equivalency mappings for CoH3.
Maps each unit to a category and faction so cross-faction comparisons work.
"""

# Format: unit_name -> (category, faction)
UNIT_CATEGORIES = {
    # ===== MAINLINE INFANTRY =====
    "Riflemen Squad":           ("mainline_infantry", "us"),
    "Grenadier Squad":          ("mainline_infantry", "wehr"),
    "Infantry Section":         ("mainline_infantry", "uk"),
    "Panzergrenadier Squad (DAK)":  ("mainline_infantry", "dak"),  # palmgren
    "Panzergrenadier Squad (WEHR)": ("elite_infantry", "wehr"),    # T3 elite, different unit

    # ===== ENGINEERS / PIONEERS =====
    "Engineer Squad":           ("engineers", "us"),
    "Pioneer Squad":            ("engineers", "wehr"),
    "Royal Engineer Section":   ("engineers", "uk"),
    "Panzerpioneer Squad":      ("engineers", "dak"),
    "Sturmpioneer Squad":       ("engineers", "wehr"),
    "Assault Engineer Squad":   ("engineers", "us"),

    # ===== HEAVY MGs =====
    "M1919 Machine Gun Team":   ("hmg", "us"),
    "MG 42 Machine Gun Team":   ("hmg", "wehr"),
    "Vickers Machine Gun Team": ("hmg", "uk"),
    "MG34 Team":                ("hmg", "dak"),

    # ===== MORTARS =====
    "M1 Mortar Team":           ("mortar", "us"),
    "GrW 34 Mortar Team":       ("mortar", "wehr"),
    "ML 3-inch Mortar Team":    ("mortar", "uk"),

    # ===== AT GUNS =====
    "M1 Anti-tank Gun Team":        ("at_gun", "us"),
    "Pak 40 Anti-tank Gun Team":    ("at_gun", "wehr"),
    "6-pounder Anti-tank Gun Team": ("at_gun", "uk"),
    "Pak 38 Anti-tank Gun Team":    ("at_gun", "dak"),
    "Flak 36 Anti-tank Gun Team":   ("at_gun", "dak"),
    "17-pounder Anti-tank Gun Team": ("at_gun", "uk"),
    "2-pounder Light Anti-tank Gun Team": ("at_gun", "uk"),  # was "2-pounder Anti-tank Gun Team"

    # ===== SCOUT / RECON INFANTRY =====
    "Scout Squad":              ("recon_infantry", "us"),
    "Pathfinder Squad":         ("recon_infantry", "us"),
    "Jäger Squad":              ("recon_infantry", "wehr"),
    "Stoßtruppen Squad":        ("recon_infantry", "wehr"),

    # ===== SNIPERS =====
    "Sniper (US)":              ("sniper", "us"),
    "Sniper (WEHR)":            ("sniper", "wehr"),

    # ===== LIGHT VEHICLES (scout cars, motorcycles) =====
    "1⁄4-ton 4x4 Truck":        ("light_vehicle", "us"),
    "M29 Weasel Recon Vehicle": ("light_vehicle", "us"),
    "Kradschützen Motorcycle Team": ("light_vehicle", "dak"),  # DAK, not Wehr
    "Kettenkrad Recon Vehicle": ("light_vehicle", "wehr"),     # Wehr, not DAK
    "221 Scout Car":            ("light_vehicle", "wehr"),
    "Dingo Light Scout Car":    ("light_vehicle", "uk"),

    # ===== ARMORED CARS =====
    "M8 Greyhound Armored Car": ("armored_car", "us"),
    "8 Rad Armored Car (DAK)":  ("armored_car", "dak"),  # DAK base T2
    "8 Rad Armored Car (WEHR)": ("armored_car", "wehr"), # Wehr Mechanized BG callin
    "Humber Armored Car":       ("armored_car", "uk"),

    # ===== HALF-TRACKS / APCs =====
    "M3 Armored Personnel Carrier": ("halftrack", "us"),
    # M3 Assault Carrier removed - it's a doctrine upgrade variant of M3 APC, not a unit
    "250 Light Carrier":            ("halftrack", "dak"),  # DAK base T0, not Wehr
    "251 Medium Carrier":           ("halftrack", "wehr"),

    # ===== LIGHT TANKS =====
    "M3 Stuart Light Tank":     ("light_tank", "uk"),  # British Lend-Lease, not USF
    "M24 Chaffee Light Tank":   ("light_tank", "us"),
    "Carro Armato M13/40 Light Tank": ("light_tank", "dak"),
    "L6/40 Light Tank":         ("light_tank", "dak"),

    # ===== MEDIUM TANKS =====
    "M4A1 Sherman Medium Tank": ("medium_tank", "us"),
    "M4(105) Sherman Bulldozer": ("assault_tank", "us"),
    "M4A1(76) Sherman Medium Tank": ("medium_tank", "us"),
    "M4A1 Sherman Whizbang":    ("medium_tank", "us"),
    "M4A3E8 Sherman Easy Eight": ("medium_tank", "us"),
    "Panzer IV Medium Tank":    ("medium_tank", "wehr"),
    "Command Panzer IV Medium Tank": ("medium_tank", "wehr"),
    "Panzer III L Medium Tank": ("medium_tank", "dak"),
    "Flammpanzer III Medium Tank": ("medium_tank", "dak"),
    "Crusader II Medium Tank":  ("medium_tank", "uk"),
    "Crusader AA Medium Tank":  ("medium_tank", "uk"),
    "M3 Grant Medium Tank":     ("medium_tank", "uk"),
    "Valentine II Medium Tank": ("medium_tank", "uk"),

    # ===== HEAVY TANKS =====
    "Tiger Heavy Tank (WEHR)":  ("heavy_tank", "wehr"),
    "Tiger Heavy Tank (DAK)":   ("heavy_tank", "dak"),  # via T0 callin tree T4 upgrade
    "Panther Heavy Tank":       ("heavy_tank", "wehr"),
    "King Tiger Heavy Tank":    ("heavy_tank", "wehr"),
    "M26 Pershing Heavy Tank":  ("heavy_tank", "us"),
    "Matilda II Heavy Tank":    ("heavy_tank", "uk"),
    "Churchill IV Heavy Tank":  ("heavy_tank", "uk"),
    "Churchill Black Prince Heavy Tank": ("heavy_tank", "uk"),
    "Churchill Crocodile Heavy Tank": ("heavy_tank", "uk"),

    # ===== TANK DESTROYERS / ASSAULT GUNS =====
    "M18 Hellcat Tank Destroyer": ("tank_destroyer", "us"),
    "Marder III Tank Destroyer":   ("tank_destroyer", "dak"),  # DAK
    "Marder III M Tank Destroyer": ("tank_destroyer", "wehr"), # Wehr
    "StuG III D Assault Gun":   ("tank_destroyer", "dak"),
    "StuG III G Assault Gun":   ("tank_destroyer", "wehr"),
    "Sturmpanzer IV Brummbär":  ("assault_tank", "wehr"),
    "Panzerjäger Squad":        ("tank_destroyer", "dak"),  # DAK T1 base infantry tank-hunter
    "Archer Tank Destroyer":    ("tank_destroyer", "uk"),
    "Sherman VC Firefly Tank Destroyer": ("tank_destroyer", "uk"),
    "Semovente da 75/18 Assault Gun": ("tank_destroyer", "dak"),

    # ===== AA / FLAK =====
    "Wirbelwind Flakpanzer":    ("aa", "wehr"),
    "Flak 30 Anti-aircraft Gun Team": ("aa", "wehr"),
    "Flakvierling Half-track":  ("aa", "dak"),
    "M16 Multiple Gun Motor Carriage": ("aa", "us"),

    # ===== ARTILLERY / ROCKETS =====
    "M8 Scott SPG":             ("artillery", "us"),
    "M3 75 mm Gun Motor Carriage": ("artillery", "us"),
    "Nebelwerfer 42 Rocket Launcher Team": ("artillery", "wehr"),
    "Walking Stuka Rocket Launcher": ("artillery", "dak"),  # DAK T3
    "Cannone da 105/28 Howitzer": ("artillery", "dak"),

    # ===== ELITE / SPECIAL INFANTRY =====
    "Bazooka Squad":            ("at_infantry", "us"),
    "Assault Grenadier Squad":  ("elite_infantry", "dak"),  # DAK T1 base
    # Kriegsmariner Squad removed - DAK Kriegsmarine BG callin, not in unit_db
    "SSF Commando Squad":       ("elite_infantry", "us"),
    "Bersaglieri Squad":        ("elite_infantry", "dak"),
    "Guastatori Squad":         ("elite_infantry", "dak"),
    "Polish Lancer Section":    ("elite_infantry", "uk"),
    "Foot Guards Section":      ("elite_infantry", "uk"),
    "Australian Light Infantry Section": ("elite_infantry", "uk"),
    "Canadian Shock Section":   ("elite_infantry", "uk"),
}


def get_category(unit: str) -> str | None:
    """Return the category of a unit, or None if uncategorized."""
    entry = UNIT_CATEGORIES.get(unit)
    return entry[0] if entry else None


def get_faction(unit: str) -> str | None:
    """Return the faction of a unit, or None if uncategorized."""
    entry = UNIT_CATEGORIES.get(unit)
    return entry[1] if entry else None


def units_in_category(category: str) -> list[str]:
    """Return all unit names in a given category."""
    return [u for u, (cat, _) in UNIT_CATEGORIES.items() if cat == category]


def all_categories() -> list[str]:
    """Return a sorted list of all categories."""
    return sorted(set(cat for cat, _ in UNIT_CATEGORIES.values()))


CATEGORY_LABELS = {
    "mainline_infantry": "Mainline Infantry",
    "engineers": "Engineers / Pioneers",
    "hmg": "Heavy MGs",
    "mortar": "Mortars",
    "at_gun": "AT Guns",
    "sniper": "Snipers",
    "recon_infantry": "Scout / Recon Infantry",
    "light_vehicle": "Light Vehicles",
    "armored_car": "Armored Cars",
    "halftrack": "Half-tracks / APCs",
    "light_tank": "Light Tanks",
    "medium_tank": "Medium Tanks",
    "heavy_tank": "Heavy Tanks",
    "tank_destroyer": "Tank Destroyers",
    "assault_tank": "Assault Tanks (Brummbär, Croc)",
    "aa": "AA / Flak",
    "artillery": "Artillery / Rockets",
    "at_infantry": "AT Infantry",
    "elite_infantry": "Elite Infantry",
}
