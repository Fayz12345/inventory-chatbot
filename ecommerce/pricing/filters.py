"""
Shared result filtering for marketplace scrapers.

Keyword searches on Amazon/eBay/Reebelo surface accessories and replacement
parts alongside whole devices (e.g. a "$8.85 screen protector" or a "$22 LCD
digitizer" outranking the actual phone). Taking a naive min(price) over those
results records the accessory price as the device floor, so we drop accessory
listings before computing the floor.
"""

# High-precision phrases that almost always describe an accessory or part,
# not a whole device. Multi-word phrases are used to avoid false positives on
# real product names (e.g. "Moto G Stylus" the phone vs a "stylus pen").
ACCESSORY_PHRASES = (
    "screen protector",
    "tempered glass",
    "digitizer",
    "lcd assembly",
    "lcd touch",
    "lcd screen",
    "replacement screen",
    "replacement lcd",
    "replacement battery",
    "phone case",
    "protective case",
    "flip case",
    "wallet case",
    "case cover",
    "back cover",
    "charging cable",
    "charger cable",
    "usb cable",
    "wall charger",
    "car charger",
    "power adapter",
    "tempered",
    # Audio accessories (headphones/earbuds/speakers rank broadly on refurb
    # marketplaces and were polluting the Reebelo floor with ~$45 items).
    "headphone",
    "earphone",
    "earbud",
    "ear buds",
    "in-ear",
    "on-ear",
    "over-ear",
    "headset",
    "soundbar",
    "speaker",
    "airpods",
    "galaxy buds",
)

# Title prefixes that mark "compatible accessory" listings ("For Motorola ...",
# "Designed for ...") rather than the device itself.
ACCESSORY_PREFIXES = (
    "for ",
    "designed for",
    "compatible with",
    "replacement for",
)


def is_accessory(title: str) -> bool:
    """True if a listing title looks like an accessory/part rather than a device."""
    if not title:
        return False
    t = title.lower().strip()
    if t.startswith(ACCESSORY_PREFIXES):
        return True
    return any(phrase in t for phrase in ACCESSORY_PHRASES)
