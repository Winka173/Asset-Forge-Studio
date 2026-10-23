"""Provisional real-world sizes by asset type (metres, width x depth x height) and scale references.

Used when no explicit, inherited, measured or model-suggested size exists, so a 349-item batch gets a sensible
scale without per-item previews. Values are provisional (provenance 'inferred'), never gameplay contracts.
"""
import re
from fastapi import APIRouter

router = APIRouter(prefix='/api/size-rules')

# (id, label, (w, d, h), English pattern, Vietnamese pattern, reference shape or None)
RULES = [
    ('castle', 'Large castle', (30, 30, 22), r'castle|fortress|citadel|stronghold|palace', r'lâu đài|thành trì|cung điện', 'castle'),
    ('cathedral', 'Temple / cathedral', (16, 24, 20), r'cathedral|temple|church', r'thánh đường|đền thờ|nhà thờ', 'house'),
    ('keep', 'Keep', (14, 14, 18), r'keep', r'tháp chính', 'tower'),
    ('barracks', 'Barracks / workshop', (10, 8, 7), r'barracks|workshop|smithy|forge|stable|tavern|inn', r'doanh trại|lò rèn|chuồng ngựa|quán trọ', 'house'),
    ('tower', 'Watchtower', (4, 4, 12), r'(?:watch)?tower|spire|lighthouse', r'tháp', 'tower'),
    ('gate', 'Gate', (8, 3, 8), r'gate(?:house)?', r'cổng', 'house'),
    ('wall', 'Wall segment', (6, 1.5, 5), r'wall', r'tường|tường thành', 'door'),
    ('house', 'Small house', (6, 5, 6), r'house|hut|cottage|cabin|shack|home', r'nhà|túp lều', 'house'),
    ('bridge', 'Bridge', (12, 4, 3), r'bridge', r'cầu', 'door'),
    ('well', 'Well / fountain', (3, 3, 3), r'well|fountain', r'giếng|đài phun', 'barrel'),
    ('shrine', 'Shrine / altar', (3, 3, 4), r'shrine|altar|obelisk|monument', r'miếu|bàn thờ|tượng đài', 'tower'),
    ('statue', 'Statue', (2, 2, 4), r'statue', r'tượng', 'human'),
    ('siege', 'Siege engine', (3, 5, 4), r'catapult|ballista|trebuchet|siege', r'máy bắn đá|công thành', 'door'),
    ('cart', 'Cart / wagon', (1.6, 3, 1.8), r'cart|wagon|carriage', r'xe kéo|xe ngựa|xe đẩy', 'door'),
    ('dragon', 'Dragon', (12, 16, 8), r'dragon|wyvern', r'rồng', 'castle'),
    ('golem', 'Golem / giant', (3, 2, 5), r'golem|titan|giant|troll|ogre', r'người đá|quỷ khổng lồ', 'human'),
    ('horse', 'Horse', (1, 2.4, 1.8), r'horse|steed|mount', r'ngựa', 'barrel'),
    ('beast', 'Wolf / beast', (0.7, 1.5, 1), r'wolf|bear|boar|beast|hound|lion|tiger', r'sói|gấu|lợn rừng|thú|chó|sư tử|hổ', 'barrel'),
    ('character', 'Character', (0.8, 0.5, 1.8), r'character|knight|swordsman|spearman|archer|soldier|warrior|guard|mage|wizard|sorcerer|priest|hero|heroine|npc|villager|king|queen|general|skeleton|zombie|paladin|assassin|thief|man|woman|human|elf|unit',
     r'kiếm sĩ|cung thủ|chiến binh|lính|pháp sư|hiệp sĩ|nhân vật|người|bộ xương|tướng|vua|nữ hoàng', 'human'),
    ('small_humanoid', 'Goblin / dwarf', (0.6, 0.4, 1.2), r'goblin|dwarf|gnome|imp', r'yêu tinh|người lùn', 'human'),
    ('tree', 'Tree', (4, 4, 7), r'tree', r'cây', 'tree'),
    ('cliff', 'Cliff / terrain piece', (10, 4, 8), r'cliff|ground|platform|terrain|road tile', r'vách đá|nền đất|đường', 'door'),
    ('rock', 'Rock', (2, 2, 1.5), r'rock|boulder|stone', r'đá|tảng đá', 'barrel'),
    ('bush', 'Bush', (1.5, 1.5, 1.2), r'bush|shrub|plant|flower|mushroom', r'bụi|cây bụi|hoa|nấm', 'tree'),
    ('crystal', 'Crystal', (0.6, 0.6, 1.2), r'crystal|gem', r'pha lê|tinh thể|đá quý', 'barrel'),
    ('chest', 'Chest', (1, 0.6, 0.7), r'chest|coffer', r'rương', 'door'),
    ('table', 'Table', (1.6, 0.9, 0.8), r'table|desk|bench|anvil', r'bàn|ghế dài|đe', 'door'),
    ('chair', 'Chair', (0.5, 0.5, 1), r'chair|stool|throne', r'ghế|ngai', 'door'),
    ('crate', 'Crate', (0.8, 0.8, 0.8), r'crate|box', r'thùng gỗ|hộp', 'door'),
    ('barrel', 'Barrel', (0.7, 0.7, 1), r'barrel|keg|cask', r'thùng|thùng rượu', 'barrel'),
    ('sack', 'Sack', (0.5, 0.4, 0.7), r'sack|bag', r'bao|túi', 'barrel'),
    ('banner', 'Banner', (1, 0.2, 3), r'banner|flag', r'cờ', 'door'),
    ('fence', 'Fence', (2, 0.2, 1.2), r'fence|palisade', r'hàng rào', 'door'),
    ('lantern', 'Lantern / torch', (0.3, 0.3, 0.5), r'lantern|lamp|torch|candle', r'đèn|đuốc|nến', 'barrel'),
    ('shield', 'Shield', (0.7, 0.1, 0.9), r'shield', r'khiên', 'door'),
    ('spear', 'Spear / staff', (0.1, 0.1, 2), r'spear|lance|pike|staff|wand', r'giáo|thương|trượng|gậy phép', 'door'),
    ('bow', 'Bow', (0.1, 0.3, 1.4), r'bow', r'cung', 'door'),
    ('sword', 'Sword', (0.2, 0.05, 1.1), r'(?:long|great|short)?sword|blade|axe|hammer|mace|dagger', r'kiếm|rìu|búa|dao găm', 'door'),
    ('potion', 'Potion / small item', (0.15, 0.15, 0.25), r'potion|bottle|flask|cup|coin|key|book|scroll|ring|amulet', r'bình|lọ|cốc|đồng xu|chìa khóa|sách|cuộn giấy|nhẫn', 'barrel'),
]
SCALE = [(r'\bboss\b|trùm', 1.5), (r'\b(?:giant|huge|colossal|enormous)\b|khổng lồ|to lớn', 1.6), (r'\b(?:small|tiny|mini)\b|nhỏ|tí hon', 0.6)]
MODIFIERS = re.compile(r'\s(?:with|holding|wearing|carrying|riding|on|of|and|for|in)\s|\s(?:với|cầm|mang|đeo|cưỡi|của|và|cho|trong)\s', re.I)
_EN = [(rule, re.compile(r'\b(?:' + rule[3] + r')s?\b', re.I)) for rule in RULES]
_VI = [(rule, re.compile(rule[4], re.I)) for rule in RULES]


def suggest(text):
    """(rule_id, (w, d, h), label) for the head noun of the subject, or None. English head noun is last, Vietnamese first."""
    if not text: return None
    text = text.replace('_', ' ')  # manifest names such as Supply_Barrel
    head = MODIFIERS.split(' ' + text + ' ', maxsplit=1)[0]
    vietnamese = [(m.start(), rule) for rule, pattern in _VI for m in [pattern.search(head)] if m]
    english = [(m.end(), rule) for rule, pattern in _EN for m in [pattern.search(head)] if m]
    if vietnamese and re.search(r'[ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ]', head, re.I):
        rule = min(vietnamese, key=lambda x: x[0])[1]
    elif english:
        rule = max(english, key=lambda x: x[0])[1]
    elif vietnamese:
        rule = min(vietnamese, key=lambda x: x[0])[1]
    else:
        return None
    # The strongest modifier wins (boss + giant must not compound into absurd sizes).
    factors = [scale for pattern, scale in SCALE if re.search(pattern, text, re.I)]
    factor = max(factors) if any(f > 1 for f in factors) else min(factors, default=1.0)
    w, d, h = (round(v * factor, 2) for v in rule[2])
    return dict(rule=rule[0], label=rule[1], dims=dict(w=w, d=d, h=h), scale_factor=factor)


@router.get('/references')
def references():
    """Scale references for the preview panel (procedural stand-ins), plus the full rule table."""
    return [dict(id=rule[0], label=f'{rule[1]} {rule[2][2]:g} m', dims=dict(w=rule[2][0], d=rule[2][1], h=rule[2][2]), shape=rule[5]) for rule in RULES]


@router.get('/suggest')
def suggest_route(text: str = ''):
    return suggest(text) or dict(rule=None, label='Unknown type', dims=dict(w=1, d=1, h=1), scale_factor=1.0)


SOURCE = 'Asset-type size rule'


def apply(item, subject):
    """Fill provisional dimensions from the type rule; never overrides explicit, inherited or measured sizes."""
    found = suggest(subject)
    if not found: return False
    provenance = item.setdefault('spec_provenance', {}); changed = False
    fixed = lambda key: item.get(key) is not None and not (provenance.get(key, {}).get('kind') == 'defaulted' or str(provenance.get(key, {}).get('source', '')).startswith(SOURCE))
    if fixed('target_height_m') and found['dims']['h']:
        # An explicit height keeps the type's proportions: a 9 m tower is narrower than the 12 m reference tower.
        ratio = item['target_height_m'] / found['dims']['h']
        found = dict(found, dims={k: round(v * ratio, 2) for k, v in found['dims'].items()}, scale_factor=round(found['scale_factor'] * ratio, 3))
    for key, axis in (('target_width_m', 'w'), ('target_depth_m', 'd'), ('target_height_m', 'h')):
        current = provenance.get(key, {})
        if item.get(key) is not None and not (current.get('kind') == 'defaulted' or str(current.get('source', '')).startswith(SOURCE)): continue
        value = float(found['dims'][axis])
        if item.get(key) != value or current.get('source') != f"{SOURCE}: {found['label']}":
            item[key] = value; changed = True
            provenance[key] = dict(kind='inferred', source=f"{SOURCE}: {found['label']}" + (f" x{found['scale_factor']:g}" if found['scale_factor'] != 1 else ''), value=value, provisional=True)
    return changed


@router.get('/batch/{batch_id}')
def batch_sizes(batch_id: str):
    """Read-only sizes for a whole batch: stored targets with provenance, or the type rule a start would apply."""
    from .batch import batch
    from engines.concept_prompt import subject_anchor
    rows = []
    for item in batch(batch_id)['items']:
        dims = {axis: item.get(key) for axis, key in (('w', 'target_width_m'), ('d', 'target_depth_m'), ('h', 'target_height_m'))}
        provenance = (item.get('spec_provenance') or {}).get('target_height_m', {})
        if dims['h'] is None:
            found = suggest(item['name'] + ' ' + subject_anchor(item.get('prompt') or ''))
            dims, provenance = (found['dims'], dict(kind='inferred', source=f"{SOURCE}: {found['label']} (preview)")) if found else (dims, dict(kind='unknown'))
        rows.append(dict(asset_id=item['asset_id'], name=item['name'], selected=item.get('selected', True), dims=dims, kind=provenance.get('kind'), source=provenance.get('source')))
    return rows


VI_NOUNS = {'kiếm sĩ': 'swordsman', 'cung thủ': 'archer', 'chiến binh': 'warrior', 'hiệp sĩ': 'knight', 'pháp sư': 'mage', 'lính': 'soldier', 'bộ xương': 'skeleton',
            'yêu tinh': 'goblin', 'người lùn': 'dwarf', 'tháp canh': 'watchtower', 'lâu đài': 'castle', 'rồng': 'dragon', 'sói': 'wolf', 'ngựa': 'horse', 'khiên': 'shield',
            'kiếm': 'sword', 'cung': 'bow', 'giáo': 'spear', 'rìu': 'axe', 'búa': 'hammer', 'thùng gỗ': 'wooden crate', 'thùng': 'barrel', 'cây': 'tree', 'nhà': 'house', 'giếng': 'well'}
VI_COLOURS = {'đỏ': 'red', 'xanh dương': 'blue', 'xanh lam': 'blue', 'xanh lá': 'green', 'vàng': 'golden', 'tím': 'purple', 'hồng': 'pink', 'đen': 'black',
              'trắng': 'white', 'cam': 'orange', 'nâu': 'brown', 'bạc': 'silver', 'xám': 'grey'}
VI_MODIFIERS = {'khổng lồ': 'giant', 'nhỏ': 'small', 'boss': 'boss', 'trùm': 'boss', 'cổ đại': 'ancient'}


def english_hint(text):
    """Deterministic English subject phrase for untranslated Vietnamese requests ('rồng đỏ khổng lồ' -> 'giant red dragon')."""
    lower = (text or '').lower()
    def found(table):
        # Longest match first at each position; overlapping shorter matches ('kiếm' inside 'kiếm sĩ') are skipped.
        hits = sorted((m.start(), -len(k), k) for k in table for m in re.finditer(re.escape(k), lower))
        spans, out = [], []
        for start, negative, k in hits:
            end = start - negative
            if any(start < e and end > s for s, e in spans): continue
            spans.append((start, end)); out.append(table[k])
        return out
    nouns = found(VI_NOUNS)
    if not nouns: return ''
    words = [*dict.fromkeys(found(VI_MODIFIERS))][:2] + [*dict.fromkeys(found(VI_COLOURS))][:2] + [nouns[0]]
    rest = [n for n in nouns[1:] if n != nouns[0]]
    return ' '.join(words) + (' with ' + ' and '.join(rest[:2]) if rest else '')
