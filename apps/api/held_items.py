"""Held weapons/shields as separate companion assets for rig-ready characters (decision 1A, 2026-10-24).

An A-pose character and a held weapon compete in SDXL (measured: the A-pose swordsman lost his sword), and a weapon
fused to the hand deforms with the rig. Characters are therefore generated empty-handed and each held item becomes
its own asset in the same batch and style, recorded with the hand socket it attaches to. Projects can opt out.
"""
import re

# (canonical item, English pattern, Vietnamese pattern, socket)
ITEMS = [
    ('sword', r'\b(?:long|great|short|broad)?swords?\b|\bblades?\b', r'kiếm(?! sĩ)', 'right_hand'),
    ('shield', r'\bshields?\b', r'khiên', 'left_hand'),
    ('bow', r'\b(?:long|short)?bows?\b', r'cung(?! thủ)', 'left_hand'),
    ('crossbow', r'\bcrossbows?\b', r'nỏ', 'right_hand'),
    ('spear', r'\b(?:spears?|lances?|pikes?|halberds?)\b', r'giáo|thương', 'right_hand'),
    ('axe', r'\b(?:battle)?axes?\b', r'rìu', 'right_hand'),
    ('hammer', r'\b(?:war)?hammers?\b|\bmaces?\b', r'búa', 'right_hand'),
    ('staff', r'\b(?:staffs?|staves|wands?)\b', r'trượng|gậy phép', 'right_hand'),
    ('dagger', r'\bdaggers?\b', r'dao găm', 'right_hand'),
]
# Items the subject's name implies even when not written ('a swordsman' carries a sword).
IMPLIED = [(r'\bswordsm(?:a|e)n\b|kiếm sĩ', 'sword'), (r'\barchers?\b|cung thủ', 'bow'), (r'\bspearm(?:a|e)n\b', 'spear'), (r'\bmages?\b|\bwizards?\b|pháp sư', 'staff')]
SOCKETS = {item: socket for item, _, _, socket in ITEMS}


def detect(text):
    """Held items in a character request, in a stable order (implied ones included)."""
    found = []
    for item, english, vietnamese, _ in ITEMS:
        if re.search(english, text, re.I) or re.search(vietnamese, text, re.I): found.append(item)
    for pattern, item in IMPLIED:
        if re.search(pattern, text, re.I) and item not in found: found.append(item)
    return found


def body_directive(items):
    return 'Both hands empty and open; no weapon, shield or held item (they are separate assets).' if items else ''


def companion_prompt(item, subject, style_hint=''):
    return f'A single {item} for a {subject}, matching its armour and materials, standalone game prop on its own, no hands or character.' + (f' {style_hint}' if style_hint else '')


def ensure_companions(value, item, project, snapshot_loader):
    """Once per character item: record held items and add each as its own batch item (same quality, engines, style)."""
    if item.get('held_items') is not None or item.get('companion_of') or project.get('separate_held_items') is False: return []
    from engines.concept_prompt import rig_class, subject_anchor
    interpretation = ((item.get('prompt_interpretation') or {}).get('chunks') or [{}])[0].get('interpretation', {})
    subject = interpretation.get('requested_subject_en') or subject_anchor(item.get('resolved_prompt') or item['prompt'])
    text = ' '.join([item['prompt'], subject, interpretation.get('translated_prompt_en', '')])
    if rig_class(subject) != 'humanoid':
        item['held_items'] = []; return []
    items = detect(text); item['held_items'] = items
    if not items: return []
    from . import studio
    from .manifest import ManifestItem
    from .automation import resolve_specs
    snapshot = snapshot_loader(); created = []
    for name in items:
        asset = studio.create_asset(studio.AssetInput(project_id=value['project_id'], name=f"{item['name']} – {name}", prompt=companion_prompt(name, subject), category='Held item'))
        row = ManifestItem(name=asset['name'], prompt=asset['prompt'], asset_id=asset['id'], preferred_engine=item.get('preferred_engine', 'auto'), candidates=1,
                           quality=item['quality'], category='Held item', confirmed=True).model_dump()
        row.update(attempt=0, started=True, version=1, quality_lock=item.get('quality_lock'), seeds=[42], companion_of=item['asset_id'], socket=SOCKETS[name],
                   interpret_prompt=False, style_reference_ids=item.get('style_reference_ids', []), intent_reference_scope=item.get('intent_reference_scope'),
                   automation=dict(enabled=True, engines=item.get('automation', {}).get('engines'), attempt=0, status='queued', stage='pending', checkpoints={}))
        resolve_specs(row, project, snapshot)
        studio.patch_resolved_specification(asset['id'], dict(attach_to=dict(parent_asset_id=item['asset_id'], socket=SOCKETS[name])))
        value['items'].append(row); created.append(row)
    studio.patch_resolved_specification(item['asset_id'], dict(held_items=[dict(item=r['name'], asset_id=r['asset_id'], socket=r['socket']) for r in created]))
    return created


def concept_conditioning(item):
    """(directives, negative terms) that keep the character's hands empty when its items are separate assets."""
    items = item.get('held_items') or []
    return ([body_directive(items)] if items else []), items
