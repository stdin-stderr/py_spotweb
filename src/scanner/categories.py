"""Spotnet category decoder — ported from spotweb/SpotCategories.php.

Category structure:
- Head category (hcat): 0=Image, 1=Sound, 2=Games, 3=Applications
- Sub-categories: encoded as string like "a0|b3|c1|d4" where first char is type, rest is number
"""

from __future__ import annotations

# Head category names
HEAD_CATEGORIES = {
    0: "Image",
    1: "Sound",
    2: "Games",
    3: "Applications",
}

# Maps head category to which subcategory type has its own description
HEADCAT_SUBCAT_MAPPING = {
    0: "d",
    1: "d",
    2: "c",
    3: "b",
}

# Subcategory type descriptions (e.g., "Format", "Source", "Genre")
SUBCAT_DESCRIPTIONS = {
    0: {"a": "Format", "b": "Source", "c": "Language", "d": "Genre", "z": "Type"},
    1: {"a": "Format", "b": "Source", "c": "Bitrate", "d": "Genre", "z": "Type"},
    2: {"a": "Platform", "b": "Format", "c": "Genre", "z": "Type"},
    3: {"a": "Platform", "b": "Genre", "z": "Type"},
}

# Short category descriptions for quick display
SHORTCAT = {
    0: {
        0: "DivX", 1: "WMV", 2: "MPG", 3: "DVD5", 4: "HD Oth", 5: "ePub",
        6: "Blu-ray", 7: "HD-DVD", 8: "WMVHD", 9: "x264HD", 10: "DVD9",
        11: "PDF", 12: "Bitmap", 13: "Vector", 14: "3D", 15: "UHD",
    },
    1: {0: "MP3", 1: "WMA", 2: "WAV", 3: "OGG", 4: "EAC", 5: "DTS", 6: "AAC", 7: "APE", 8: "FLAC"},
    2: {
        0: "WIN", 1: "MAC", 2: "TUX", 3: "PS", 4: "PS2", 5: "PSP", 6: "XBX",
        7: "360", 8: "GBA", 9: "GC", 10: "NDS", 11: "Wii", 12: "PS3",
        13: "WinPh", 14: "iOS", 15: "Android", 16: "3DS", 17: "PS4", 18: "XB1",
    },
    3: {0: "WIN", 1: "MAC", 2: "TUX", 3: "OS/2", 4: "WinPh", 5: "NAV", 6: "iOS", 7: "Android"},
}

# Full category tree — format: [name, allowed_types, historical_types]
CATEGORIES = {
    0: {  # Image/Video
        "a": {  # Format
            0: ["DivX", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            1: ["WMV", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            2: ["MPG", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            3: ["DVD5", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            4: ["HD other", [], ["z0", "z1", "z3"]],
            5: ["ePub", ["z2"], ["z2"]],
            6: ["Blu-ray", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            7: ["HD-DVD", [], ["z0", "z1", "z3"]],
            8: ["WMVHD", [], ["z0", "z1", "z3"]],
            9: ["x264", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            10: ["DVD9", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            11: ["PDF", ["z2"], ["z2"]],
            12: ["Bitmap", ["z4"], ["z4"]],
            13: ["Vector", ["z4"], ["z4"]],
            14: ["3D", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            15: ["UHD", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
        },
        "b": {  # Source
            0: ["CAM", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            1: ["(S)VCD", [], ["z0", "z1", "z3"]],
            2: ["Promo", [], ["z0", "z1", "z3"]],
            3: ["Retail", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            4: ["TV", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            5: ["-", [], []],
            6: ["Satellite", [], ["z0", "z1", "z3"]],
            7: ["R5", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            8: ["Telecine", [], ["z0", "z1", "z3"]],
            9: ["Telesync", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            10: ["Scan", ["z2"], ["z2"]],
            11: ["WEB-DL", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            12: ["WEBRip", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            13: ["HDRip", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
        },
        "c": {  # Language
            0: ["No subtitles", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            1: ["Dutch subtitles (external)", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            2: ["Dutch subtitles (builtin)", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            3: ["English subtitles (external)", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            4: ["English subtitles (builtin)", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            5: ["-", [], []],
            6: ["Dutch subtitles (available)", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            7: ["English subtitles (available)", ["z0", "z1", "z3"], ["z0", "z1", "z3"]],
            8: ["-", [], []],
            9: ["-", [], []],
            10: ["English audio/written", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            11: ["Dutch audio/written", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            12: ["German audio/written", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            13: ["French audio/written", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            14: ["Spanish audio/written", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            15: ["Asian audio/written", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
        },
        "d": {  # Genre (merged with erotica)
            0: ["Action", ["z0", "z1"], ["z0", "z1"]], 1: ["Adventure", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            2: ["Animation", ["z0", "z1"], ["z0", "z1"]], 3: ["Cabaret", ["z0", "z1"], ["z0", "z1"]],
            4: ["Comedy", ["z0", "z1"], ["z0", "z1"]], 5: ["Crime", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            6: ["Documentary", ["z0", "z1"], ["z0", "z1"]], 7: ["Drama", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            8: ["Family", ["z0", "z1"], ["z0", "z1"]], 9: ["Fantasy", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            10: ["Arthouse", ["z0", "z1"], ["z0", "z1"]], 11: ["Television", ["z0", "z1"], ["z0", "z1"]],
            12: ["Horror", ["z0", "z1"], ["z0", "z1"]], 13: ["Music", ["z0", "z1"], ["z0", "z1"]],
            14: ["Musical", ["z0", "z1"], ["z0", "z1"]], 15: ["Mystery", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            16: ["Romance", ["z0", "z1", "z2"], ["z0", "z1", "z2"]], 17: ["Science Fiction", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            18: ["Sport", ["z0", "z1"], ["z0", "z1"]], 19: ["Short movie", ["z0", "z1"], ["z0", "z1"]],
            20: ["Thriller", ["z0", "z1", "z2"], ["z0", "z1", "z2"]], 21: ["War", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            22: ["Western", ["z0", "z1"], ["z0", "z1"]], 23: ["Erotica (hetero)", [], ["z3"]],
            24: ["Erotica (gay male)", [], ["z3"]], 25: ["Erotica (gay female)", [], ["z3"]],
            26: ["Erotica (bi)", [], ["z3"]], 27: ["-", [], []],
            28: ["Asian", ["z0", "z1"], ["z0", "z1"]], 29: ["Anime", ["z0", "z1"], ["z0", "z1"]],
            30: ["Cover", ["z2"], ["z2"]], 31: ["Comicbook", ["z2"], ["z2"]],
            32: ["Cartoons", ["z2"], ["z2"]], 33: ["Youth", ["z2"], ["z2"]],
            34: ["Business", ["z2"], ["z2"]], 35: ["Computer", ["z2"], ["z2"]],
            36: ["Hobby", ["z2"], ["z2"]], 37: ["Cooking", ["z2"], ["z2"]],
            38: ["Handwork", ["z2"], ["z2"]], 39: ["Craftwork", ["z2"], ["z2"]],
            40: ["Health", ["z2"], ["z2"]], 41: ["History", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            42: ["Psychology", ["z2"], ["z2"]], 43: ["Newspaper", ["z2"], ["z2"]],
            44: ["Magazine", ["z2"], ["z2"]], 45: ["Science", ["z2"], ["z2"]],
            46: ["Female", ["z2"], ["z2"]], 47: ["Religion", ["z2"], ["z2"]],
            48: ["Roman", ["z2"], ["z2"]], 49: ["Biography", ["z2"], ["z2"]],
            50: ["Detective", ["z0", "z1", "z2"], ["z0", "z1", "z2"]], 51: ["Animals", ["z0", "z1", "z2"], ["z0", "z1", "z2"]],
            52: ["Humor", ["z0", "z1", "z2"], ["z0", "z1", "z2"]], 53: ["Travel", ["z2"], ["z2"]],
            54: ["True story", ["z0", "z1"], ["z0", "z1"]], 55: ["Non-fiction", ["z2"], ["z2"]],
            56: ["Politics", [], []], 57: ["Poetry", ["z2"], ["z2"]],
            58: ["Fairy tale", ["z2"], ["z2"]], 59: ["Technical", ["z2"], ["z2"]],
            60: ["Art", ["z2"], ["z2"]], 72: ["Bi", ["z3"], ["z3"]],
            73: ["Lesbian", ["z3"], ["z3"]], 74: ["Homo", ["z3"], ["z3"]],
            75: ["Hetero", ["z3"], ["z3"]], 76: ["Amature", ["z3"], ["z3"]],
            77: ["Group", ["z3"], ["z3"]], 78: ["POV", ["z3"], ["z3"]],
            79: ["Solo", ["z3"], ["z3"]], 80: ["Young", ["z3"], ["z3"]],
            81: ["Soft", ["z3"], ["z3"]], 82: ["Fetish", ["z3"], ["z3"]],
            83: ["Old", ["z3"], ["z3"]], 84: ["Fat", ["z3"], ["z3"]],
            85: ["SM", ["z3"], ["z3"]], 86: ["Rough", ["z3"], ["z3"]],
            87: ["Dark", ["z3"], ["z3"]], 88: ["Hentai", ["z3"], ["z3"]],
            89: ["Outside", ["z3"], ["z3"]],
        },
        "z": {0: "Movie", 1: "Series", 2: "Book", 3: "Erotica", 4: "Picture"},
    },
    1: {  # Sound
        "a": {  # Format
            0: ["MP3", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            1: ["WMA", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            2: ["WAV", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            3: ["OGG", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            4: ["EAC", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            5: ["DTS", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            6: ["AAC", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            7: ["APE", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            8: ["FLAC", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
        },
        "b": {  # Source
            0: ["CD", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            1: ["Radio", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            2: ["Compilation", [], ["z0", "z1", "z2", "z3"]],
            3: ["DVD", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            4: ["Other", [], ["z0", "z1", "z2", "z3"]],
            5: ["Vinyl", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            6: ["Stream", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
        },
        "c": {  # Bitrate
            0: ["Variable", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            1: ["< 96kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            2: ["96kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            3: ["128kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            4: ["160kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            5: ["192kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            6: ["256kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            7: ["320kbit", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            8: ["Lossless", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            9: ["Other", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
        },
        "d": {  # Genre (music)
            0: ["Blues", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            1: ["Compilation", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            2: ["Cabaret", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            3: ["Dance", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            4: ["Diverse", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            5: ["Hardcore", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            6: ["World", [], ["z0", "z1", "z2", "z3"]],
            7: ["Jazz", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            8: ["Youth", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            9: ["Classical", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            10: ["Kleinkunst", [], ["z0", "z1", "z2", "z3"]],
            11: ["Dutch", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            12: ["New Age", [], ["z0", "z1", "z2", "z3"]],
            13: ["Pop", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            14: ["RnB", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            15: ["Hiphop", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            16: ["Reggae", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            17: ["Religious", [], ["z0", "z1", "z2", "z3"]],
            18: ["Rock", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            19: ["Soundtracks", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            20: ["Other", [], ["z0", "z1", "z2", "z3"]],
            21: ["Hardstyle", [], ["z0", "z1", "z2", "z3"]],
            22: ["Asian", [], ["z0", "z1", "z2", "z3"]],
            23: ["Disco", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            24: ["Classics", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            25: ["Metal", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            26: ["Country", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            27: ["Dubstep", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            28: ["Nederhop", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            29: ["DnB", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            30: ["Electro", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            31: ["Folk", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            32: ["Soul", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            33: ["Trance", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            34: ["Balkan", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            35: ["Techno", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            36: ["Ambient", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            37: ["Latin", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
            38: ["Live", ["z0", "z1", "z2", "z3"], ["z0", "z1", "z2", "z3"]],
        },
        "z": {0: "Album", 1: "Liveset", 2: "Podcast", 3: "Audiobook"},
    },
    2: {  # Games
        "a": {  # Platform
            0: ["Windows", ["zz"], ["zz"]], 1: ["Macintosh", ["zz"], ["zz"]],
            2: ["Linux", ["zz"], ["zz"]], 3: ["Playstation", ["zz"], ["zz"]],
            4: ["Playstation 2", ["zz"], ["zz"]], 5: ["PSP", ["zz"], ["zz"]],
            6: ["Xbox", ["zz"], ["zz"]], 7: ["Xbox 360", ["zz"], ["zz"]],
            8: ["Gameboy Advance", ["zz"], ["zz"]], 9: ["Gamecube", ["zz"], ["zz"]],
            10: ["Nintendo DS", ["zz"], ["zz"]], 11: ["Nintento Wii", ["zz"], ["zz"]],
            12: ["Playstation 3", ["zz"], ["zz"]], 13: ["Windows Phone", ["zz"], ["zz"]],
            14: ["iOS", ["zz"], ["zz"]], 15: ["Android", ["zz"], ["zz"]],
            16: ["Nintendo 3DS", ["zz"], ["zz"]], 17: ["Playstation 4", ["zz"], ["zz"]],
            18: ["XBox 1", ["zz"], ["zz"]],
        },
        "b": {  # Format
            0: ["ISO", [], ["zz"]], 1: ["Rip", ["zz"], ["zz"]],
            2: ["Retail", ["zz"], ["zz"]], 3: ["DLC", ["zz"], ["zz"]],
            4: ["", [], []], 5: ["Patch", ["zz"], ["zz"]],
            6: ["Crack", ["zz"], ["zz"]],
        },
        "c": {  # Genre
            0: ["Action", ["zz"], ["zz"]], 1: ["Adventure", ["zz"], ["zz"]],
            2: ["Strategy", ["zz"], ["zz"]], 3: ["Roleplaying", ["zz"], ["zz"]],
            4: ["Simulation", ["zz"], ["zz"]], 5: ["Race", ["zz"], ["zz"]],
            6: ["Flying", ["zz"], ["zz"]], 7: ["Shooter", ["zz"], ["zz"]],
            8: ["Platform", ["zz"], ["zz"]], 9: ["Sport", ["zz"], ["zz"]],
            10: ["Child/youth", ["zz"], ["zz"]], 11: ["Puzzle", ["zz"], ["zz"]],
            12: ["Other", [], ["zz"]], 13: ["Boardgame", ["zz"], ["zz"]],
            14: ["Cards", ["zz"], ["zz"]], 15: ["Education", ["zz"], ["zz"]],
            16: ["Music", ["zz"], ["zz"]], 17: ["Family", ["zz"], ["zz"]],
        },
        "z": {"z": "everything"},
    },
    3: {  # Applications
        "a": {  # Platform
            0: ["Windows", ["zz"], ["zz"]], 1: ["Macintosh", ["zz"], ["zz"]],
            2: ["Linux", ["zz"], ["zz"]], 3: ["OS/2", ["zz"], ["zz"]],
            4: ["Windows Phone", ["zz"], ["zz"]], 5: ["Navigation systems", ["zz"], ["zz"]],
            6: ["iOS", ["zz"], ["zz"]], 7: ["Android", ["zz"], ["zz"]],
        },
        "b": {  # Category
            0: ["Audio", ["zz"], ["zz"]], 1: ["Video", ["zz"], ["zz"]],
            2: ["Graphics", ["zz"], ["zz"]], 3: ["CD/DVD Tools", [], ["zz"]],
            4: ["Media players", [], ["zz"]], 5: ["Rippers & Encoders", [], []],
            6: ["Plugins", [], ["zz"]], 7: ["Database tools", [], ["zz"]],
            8: ["Email software", [], ["zz"]], 9: ["Photo", [], ["zz"]],
            10: ["Screensavers", [], ["zz"]], 11: ["Skin software", [], ["zz"]],
            12: ["Drivers", [], ["zz"]], 13: ["Browsers", [], ["zz"]],
            14: ["Download managers", [], []], 15: ["Download", ["zz"], ["zz"]],
            16: ["Usenet software", [], ["zz"]], 17: ["RSS Readers", [], ["zz"]],
            18: ["FTP software", [], ["zz"]], 19: ["Firewalls", [], ["zz"]],
            20: ["Antivirus software", [], ["zz"]], 21: ["Antispyware software", [], ["zz"]],
            22: ["Optimization software", [], ["zz"]], 23: ["Security software", ["zz"], ["zz"]],
            24: ["System software", ["zz"], ["zz"]], 25: ["Other", [], ["zz"]],
            26: ["Educational", ["zz"], ["zz"]], 27: ["Office", ["zz"], ["zz"]],
            28: ["Internet", ["zz"], ["zz"]], 29: ["Communication", ["zz"], ["zz"]],
            30: ["Development", ["zz"], ["zz"]], 31: ["Spotnet", ["zz"], ["zz"]],
        },
        "z": {"z": "everything"},
    },
}


def cat2desc(hcat: int, cat: str) -> str:
    """Convert a category code to its description.

    Args:
        hcat: Head category (0-3)
        cat: Category code like "a0" or "b3|c1" (pipe-separated list)

    Returns:
        Description string or "-" if not found
    """
    if not cat:
        return ""

    cat_list = cat.split("|")
    cat = cat_list[0]

    if not cat or not cat[0]:
        return ""

    cat_type = cat[0]
    try:
        nr = int(cat[1:])
    except (ValueError, IndexError):
        return "-"

    try:
        if cat_type == "z":
            return str(CATEGORIES[hcat][cat_type][nr])
        else:
            return CATEGORIES[hcat][cat_type][nr][0]
    except (KeyError, IndexError):
        return "-"


def cat2short_desc(hcat: int, cat: str) -> str:
    """Get short description for a category."""
    if not cat:
        return ""

    cat_list = cat.split("|")
    cat = cat_list[0]

    if not cat or not cat[0]:
        return ""

    try:
        nr = int(cat[1:])
    except (ValueError, IndexError):
        return "-"

    try:
        return SHORTCAT[hcat][nr]
    except (KeyError, IndexError):
        return "-"


def subcat_description(hcat: int, ch: str) -> str:
    """Get the description for a subcategory type (e.g., 'Format', 'Source')."""
    try:
        return SUBCAT_DESCRIPTIONS[hcat][ch]
    except KeyError:
        return "-"


def head_cat2desc(cat: int) -> str:
    """Convert head category number to name."""
    return HEAD_CATEGORIES.get(cat, "-")


def create_subcat_z(hcat: int, subcats: str) -> str:
    """Determine z-category (type) from subcategories.

    z-categories are only for video (0) and audio (1).
    Returns a pipe-separated string like "z0|" or "z1|"
    """
    if hcat not in (0, 1):
        return ""

    subcat_list = [s.strip() for s in subcats.split("|") if s.strip()]

    if hcat == 0:  # Video
        # Check for erotica
        erotica_codes = {
            "d23", "d24", "d25", "d26", "d72", "d73", "d74", "d75",
            "d76", "d77", "d78", "d79", "d80", "d81", "d82", "d83",
            "d84", "d85", "d86", "d87", "d88", "d89",
        }
        if any(sc in erotica_codes for sc in subcat_list):
            return "z3|"

        # Check for series
        if "b4" in subcat_list or "d11" in subcat_list:
            return "z1|"

        # Check for books
        if "a5" in subcat_list or "a11" in subcat_list:
            return "z2|"

        # Check for pictures
        if "a12" in subcat_list or "a13" in subcat_list:
            return "z4|"

        # Default to movie
        return "z0|"

    elif hcat == 1:  # Audio
        return "z0|"

    return ""


def spotnet_to_newznab_categories(spotnet_cat: int, subcats: str) -> list[int]:
    """Convert spotnet XML category + subcategories to Newznab category IDs.

    spotnet_cat: Raw Spotnet XML Category (0=Video, 1=Audio, 2=Image/Ebook, 3=Applications)
    subcats: Pipe-separated subcategory codes from the tree (format: a0|b3|c1|d4)

    Returns list of Newznab category IDs (e.g., [7000, 7020] for Image > PDF).
    """
    newznab_ids = []

    # Map Spotnet XML categories to primary Newznab IDs
    # Note: Spotnet XML Category differs from the subcategory tree structure
    spotnet_cat_to_newznab = {
        0: 2000,  # Video/Movie -> Movies
        1: 3000,  # Audio -> Audio
        2: 7000,  # Image/Ebook -> Other
        3: 4000,  # Applications -> PC
    }

    if spotnet_cat not in spotnet_cat_to_newznab:
        return [7000]

    newznab_ids.append(spotnet_cat_to_newznab[spotnet_cat])

    if not subcats:
        return newznab_ids

    subcat_list = [s.strip() for s in subcats.split("|") if s.strip()]

    if spotnet_cat == 0:  # Video
        # Check for specific movie/TV subcategories
        for sc in subcat_list:
            if sc.startswith("b"):
                try:
                    src_num = int(sc[1:])
                    # TV source (b4) -> TV
                    if src_num == 4:
                        if 5000 not in newznab_ids:
                            newznab_ids = [5000]  # Replace movie with TV
                except ValueError:
                    pass

    elif spotnet_cat == 1:  # Audio
        # MP3 (a0) -> MP3, FLAC (a8) -> Lossless
        for sc in subcat_list:
            if sc.startswith("a"):
                try:
                    fmt_num = int(sc[1:])
                    if fmt_num == 0:  # MP3
                        if 3010 not in newznab_ids:
                            newznab_ids.append(3010)
                    elif fmt_num == 8:  # FLAC
                        if 3040 not in newznab_ids:
                            newznab_ids.append(3040)
                except ValueError:
                    pass

    elif spotnet_cat == 2:  # Image/Ebook
        # Check primary format subcategories for more specific mappings
        for sc in subcat_list:
            if sc.startswith("a"):
                try:
                    fmt_num = int(sc[1:])
                    # PDF (a11) and ePub (a5) -> Ebook
                    if fmt_num in (5, 11):
                        if 7020 not in newznab_ids:
                            newznab_ids.append(7020)
                except ValueError:
                    pass

    return newznab_ids


def spotnet_category_path(spotnet_cat: int, subcats: str) -> str:
    """Build human-readable category path like 'Image > PDF'.

    spotnet_cat: Raw Spotnet XML Category (0=Video, 1=Audio, 2=Image/Ebook, 3=Applications)
    subcats: Pipe-separated subcategory codes
    """
    # Map Spotnet XML Category to display name
    spotnet_cat_names = {
        0: "Video",
        1: "Audio",
        2: "Image",
        3: "Applications",
    }

    path = spotnet_cat_names.get(spotnet_cat, "-")

    if not subcats:
        return path

    subcat_list = [s.strip() for s in subcats.split("|") if s.strip()]
    if not subcat_list:
        return path

    first_sc = subcat_list[0]
    if not first_sc:
        return path

    # Determine which subcategory tree this belongs to based on Spotnet category
    tree_hcat = None
    if spotnet_cat == 0:  # Video uses tree 0 (Image)
        tree_hcat = 0
    elif spotnet_cat == 1:  # Audio uses tree 1 (Sound)
        tree_hcat = 1
    elif spotnet_cat == 2:  # Image/Ebook uses tree 0 (Image)
        tree_hcat = 0
    elif spotnet_cat == 3:  # Applications uses tree 3 (Applications)
        tree_hcat = 3

    if tree_hcat is not None:
        desc = cat2desc(tree_hcat, first_sc)
        if desc and desc != "-":
            return f"{path} > {desc}"

    return path
