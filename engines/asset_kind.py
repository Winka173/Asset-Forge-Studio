"""What kind of asset a request is, chosen by the user or detected from its subject (Auto).

The kind decides the type-specific steps: buildings are drawn and checked at human scale and wells get water;
characters and creatures get a rig-friendly pose, an auto-rig and an animation offer; props, vehicles and nature do
neither. Auto keeps the subject detection that was spread over these steps, so an explicit choice only fixes misses.
"""
import re

from .concept_prompt import BUILDING, DWELLING, FORTIFIED, ENTERABLE, rig_class, subject_anchor

KINDS = ('auto', 'building', 'character', 'creature', 'prop', 'vehicle', 'nature')
LABELS = dict(building='Building', character='Character', creature='Creature / animal', prop='Prop / item', vehicle='Vehicle / machine', nature='Nature / terrain')
VEHICLE = re.compile(r'\b(?:cart|wagon|carriage|ship|boat|raft|catapult|ballista|trebuchet|siege engine|chariot|airship|cannon)s?\b|xe kéo|xe ngựa|thuyền|tàu|máy bắn đá', re.I)
NATURE = re.compile(r'\b(?:tree|bush|shrub|rock|boulder|cliff|terrain|ground|grass|flower|mushroom|vine|log|stump|crystal cluster|hill|mountain)s?\b|cây|bụi|đá tảng|vách đá|hoa|nấm|đồi|núi', re.I)


def detect(text):
    """Auto: the kind of the request's subject (its heading/first words), never 'auto'."""
    return detect_strict(text) or 'prop'


def detect_strict(text):
    """The kind only when a subject word says so; None when nothing matched (Prop is then a guess, not evidence)."""
    anchor = subject_anchor(text or '')
    rig = rig_class(anchor)
    if rig: return 'character' if rig == 'humanoid' else 'creature'
    if BUILDING.search(anchor) or DWELLING.search(anchor) or FORTIFIED.search(anchor) or ENTERABLE.search(anchor):
        # Cliffs, terrain tiles and platforms match the building words but are ground pieces.
        return 'nature' if NATURE.search(anchor) and not (DWELLING.search(anchor) or FORTIFIED.search(anchor) or ENTERABLE.search(anchor)) else 'building'
    if VEHICLE.search(anchor): return 'vehicle'
    if NATURE.search(anchor): return 'nature'
    return None


def effective(kind, text):
    return kind if kind in KINDS and kind != 'auto' else detect(text)


def of_asset(asset, item=None):
    """The kind for an asset (a batch item's choice wins over the asset's)."""
    chosen = (item or {}).get('kind') or asset.get('kind') or 'auto'
    return effective(chosen, (item or {}).get('prompt') or asset.get('prompt') or asset.get('name', ''))


def mismatch(chosen, text):
    """The detected kind when an explicit choice contradicts a clear subject word, else None."""
    if chosen in (None, '', 'auto'): return None
    strict = detect_strict(text)
    return strict if strict and strict != chosen else None
