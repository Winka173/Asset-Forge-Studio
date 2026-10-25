"""Image conditioning is separate from source text and evaluator instructions."""
import re

# Without an image anchor SDXL often draws a set of items; measured: the extra terms turned a potion lineup into one bottle.
NEGATIVE_PROMPT=('display pedestal, plinth, display stand, contact sheet, multiple objects, set of items, assortment, collection, scattered objects, duplicates, item lineup, icon sheet, pattern, wallpaper, split screen, grid, collage, multiple views, turnaround, '
    'orthographic sheet, inset image, diagram, poster, decorative border, text, caption, watermark, logo, '
    'landscape, scenery, forest, clouds, sky, cropped, cut off, blurry, low quality, broken perspective')

# Policy 3: description first, framing last (legacy; locked effective configs keep it).
# Policy 4: subject + framing + short style in the first CLIP window, then the complete description.
# Policy 5: as 4, but a manifest heading restated later with its description ('NAME. Tiered fountain ...') anchors on that description.
# Policy 6: as 5, and a manifest-format prompt (markdown sections) conditions the image only on its restated visual
# description. Measured: its ~26 windows of production-contract text overpowered the subject in cross-attention
# (trees and fountains rendered as towers with mean or first-window pooling alike). Any description is also bounded to
# leading sentences within CONDITIONING_WORDS (~3 CLIP windows); a 1,766-word planner rewrite drowned a tree the same way.
# The original prompt and its interpretation stay immutable in the asset/spec.
# Long prompts are encoded in 75-token windows and mean-pooled, so late anchors lose influence.
# Policy 7: characters and creatures get a rig-friendly neutral pose (arms/limbs clear of the body) unless the user asked for a pose.
# Policy 8: rig framings keep the whole body inside the frame (measured: spread wings and pedestals pushed policy-7 dragons
# past the frame edges, so only an off-colour dragon stayed eligible) and stand on the ground without a base.
# Policy 9: buildings are drawn at human scale (an entrance door a person walks through, windows at people height) unless
# the request is giant; dwellings (house, shop, inn) keep away from castle/fortress massing and every building from ruins
# unless asked. Measured: a "HOUSE specialization" with a castle reference came out as a four-tower castle with a tiny
# door, and a merchant estate as a ruin with broken pieces stuck to it.
COMPOSITION_POLICY=9
DWELLING=re.compile(r'\b(?:house|home|hut|cottage|cabin|dwelling|estate|villa|manor|shop|store|inn|tavern|bakery|smithy|forge|farmhouse|mill|stable|workshop|residence)s?\b|nhà|quán|tiệm|biệt thự|dinh thự',re.I)
FORTIFIED=re.compile(r'\b(?:castle|fortress|fort|citadel|keep|stronghold|tower|turret)s?\b|lâu đài|pháo đài|tháp',re.I)
GIANT=re.compile(r'\b(?:giant|colossal|titanic|gigantic|enormous|huge)\b|khổng lồ|to lớn|siêu lớn',re.I)
RUINED=re.compile(r'\b(?:ruin|ruined|ruins|broken|destroyed|abandoned|crumbling|damaged)\b|đổ nát|tàn tích|hoang tàn|bị phá',re.I)
ENTERABLE=re.compile(r'\b(?:temple|shrine|chapel|church|barracks|building|hall|guild|library|academy|lodge|warehouse|granary)s?\b|đền|chùa|nhà',re.I)
# Chosen buildings people do not walk into keep no door rule.
OPEN_STRUCTURE=re.compile(r'\b(?:well|fountain|wall|bridge|statue|fence|platform|pillar|obelisk|monument|altar|gate)s?\b|giếng|đài phun|tường|cầu|tượng|hàng rào|cột',re.I)
HUMAN_SCALE='human-scale building, entrance door sized for a person to walk through, windows at people height'
CONDITIONING_WORDS=160
FRAMING='single standalone 3D game asset, three-quarter view, full object centered with clear margin, plain neutral studio background'
# 2D sprites are cut out from a flat background, so the framing asks for no cast shadow and an even backdrop.
# Arms-away poses keep limbs from fusing with the torso in image-to-3D, which auto-rigging needs (A-pose literature and vendor guidance).
RIG_FRAMINGS={'humanoid':'single standalone 3D game character, zoomed out, full body centered with generous margin on all sides, front view, neutral A-pose with both arms held away from the body, legs slightly apart, standing directly on the ground with no base, plain neutral studio background',
    'creature':'single standalone 3D game creature, zoomed out, whole body centered with generous margin on all sides, three-quarter view, neutral standing pose with legs straight under the body, wings half-spread, mouth closed, tail extended, standing directly on the ground with no base, plain neutral studio background'}
HUMANOID=re.compile(r'\b(?:character|knight|swordsman|spearman|archer|soldier|warrior|guard|mage|wizard|sorcerer|priest|hero|heroine|npc|villager|king|queen|general|skeleton|zombie|goblin|orc|elf|dwarf|human|man|woman|paladin|assassin|thief)s?\b|'
    r'kiếm sĩ|cung thủ|chiến binh|lính|pháp sư|hiệp sĩ|nhân vật|người|bộ xương|tướng|vua|nữ hoàng',re.I)
CREATURE=re.compile(r'\b(?:dragon|wyvern|wolf|bear|beast|monster|golem|spider|bird|horse|griffin|gryphon|lion|tiger|boar|serpent|snake|creature|dinosaur|demon|troll|ogre|giant)s?\b|'
    r'rồng|sói|gấu|quái|quái vật|nhện|chim|ngựa|sư tử|hổ|rắn|ác quỷ|khổng lồ',re.I)
BUILDING=re.compile(r'\b(?:tower|castle|keep|house|hut|wall|gate|shrine|temple|well|fountain|barracks|building|bridge|statue|tile|fence|cliff|platform)s?\b|tháp|lâu đài|nhà|tường|cổng|đền|giếng|cầu|tượng',re.I)
POSED=re.compile(r'\b(?:pose|posing|attacking|swinging|flying|running|jumping|sitting|kneeling|leaping|casting|roaring|charging)\b|tư thế|đang |vung|bay |chạy|nhảy|ngồi|quỳ',re.I)


def rig_class(text):
    """humanoid / creature for animation-ready framing; None for props, buildings, or when the user specified a pose."""
    if not text or POSED.search(text) or BUILDING.search(text):return None  # 'archer tower' is a building, never a rig pose
    creature,humanoid=CREATURE.search(text),HUMANOID.search(text)
    if creature and (not humanoid or creature.start()<humanoid.start()):return 'creature'
    return 'humanoid' if humanoid else None


FRAMINGS={'asset_3d':FRAMING,'sprite_2d':'single 2D game sprite of one object, centered, full object visible with clear margin, flat even light grey background, no cast shadow, no ground'}


def _clean(description):
    # SDXL does not reliably understand negation. Put unwanted composition in the
    # negative conditioning rather than mentioning panels/scenery in the positive.
    # Planning models occasionally restate forbidden layout keywords positively
    # inside a negated sentence. SDXL often renders those anyway. Move only known
    # composition exclusions; original prompt/translation remain immutable.
    description=re.sub(r'\bNo\s+(?:surrounding\s+)?(?:scenery|panels|poster layouts)[^.\n]*(?:\.|$)','',description,flags=re.I)
    return re.sub(r'\bInferred ordinary details include:\s*','',description,flags=re.I).strip()


def _heading(description):
    first=re.split(r'(?<=[.!?])\s+|\n',description.strip(),maxsplit=1)[0]
    # Manifest headings carry markdown and stable IDs ('# BLD_CASTLE_T1 — CASTLE T1 Keep'); keep only the readable subject.
    first=re.sub(r'[#*_`>]+',' ',re.sub(r'\b[A-Z0-9]+(?:_[A-Za-z0-9]+)+\b',' ',first))
    return re.sub(r'^[\s\W]+','',first)


def _restated(name,description):
    """The later line that restates the heading with the visual description ('MANA WELL T2. Tiered fountain ...')."""
    pattern=r'[\s_]+'.join(re.escape(word) for word in name.split())
    body=description.strip().split('\n',1)[1] if '\n' in description.strip() else ''
    found=re.search(r'^\s*'+pattern+r'\s*[.:—-]\s*(\S[^\n]*)',body,flags=re.I|re.M)
    return found.group(1).strip() if found else None


def subject_anchor(description,max_words=24,policy=COMPOSITION_POLICY):
    """First sentence of the description, bounded so the anchor stays inside the first CLIP window."""
    first=_heading(description)
    name=first.rstrip(',;:.!? ')
    if policy>=5 and name:
        # A bare name ('MANA WELL T2 Runic Conduit') says nothing about shape; manifests restate it with the visual description.
        restated=_restated(name,description)
        if restated:first=name+': '+re.split(r'(?<=[.!?])\s+',restated,maxsplit=1)[0]
    words=first.split()
    return ' '.join(words[:max_words]).rstrip(',;:.!?')


def _bounded(description,max_words=CONDITIONING_WORDS):
    """Leading whole sentences within the concept conditioning budget (long rewrites drown the subject)."""
    kept=[];count=0
    for sentence in re.split(r'(?<=[.!?])\s+',description.strip()):
        words=len(sentence.split())
        if kept and count+words>max_words:break
        kept.append(sentence);count+=words
    return ' '.join(kept)


def short_style(style,max_words=18):
    return ' '.join(style.replace(';',',').split()[:max_words]).rstrip(',;:')


def compose(description,style='',quality=None,policy=COMPOSITION_POLICY,directives=(),framing='asset_3d',kind='auto'):
    """Directives (reference colours, subject hints, repair instructions) are kept verbatim; only the description is bounded."""
    directives=[d.strip() for d in directives if d and d.strip()]
    if policy<6 and directives:description='\n'.join([description,*directives]);directives=[]  # earlier policies appended them to the text
    description=_clean(description)
    detail=('\nProduction game-asset beauty render, finely resolved surface relief, readable crafted edges, '
        'rich coherent material variation and carefully finished textures. Preserve the requested stylization.') if quality=='Maximum' else ''
    if policy==3:
        return (description+('\nVisual style: '+style if style else '')+detail+
            '\nA single standalone 3D game asset, zoomed out, three-quarter view, '
            'full object centered with clear margin, plain neutral studio background.'),NEGATIVE_PROMPT
    anchor=subject_anchor(description,policy=policy)
    if policy>=6:
        if re.search(r'^#{1,3}\s',description,flags=re.M):
            name=_heading(description).rstrip(',;:.!? ');restated=name and _restated(name,description)
            if restated:description=f'{name}. {restated}'
        description='\n'.join([_bounded(description),*directives])
    rig=rig_for(anchor,kind) if policy>=7 and framing=='asset_3d' else None
    # An explicit asset type (engines/asset_kind.py) replaces the subject detection; Auto keeps it.
    scale,negative=building_scale(anchor,forced=kind=='building') if policy>=9 and framing=='asset_3d' and not rig and kind in ('auto','building') else ('',NEGATIVE_PROMPT)
    head=f'{anchor}, {RIG_FRAMINGS[rig] if rig else FRAMINGS[framing]}'+(f', {scale}' if scale else '')+(f', {short_style(style)}' if style else '')+'.'
    return (head+'\n'+description+('\nVisual style: '+style if style else '')+detail),negative


def rig_for(anchor,kind='auto'):
    """Pose class for the concept: chosen character/creature, none for other chosen kinds, detected under Auto."""
    if kind in ('character','creature'):return 'humanoid' if kind=='character' else 'creature'
    return rig_class(anchor) if kind in ('auto','',None) else None


def building_scale(anchor,forced=False):
    """(extra framing, negative prompt) for a building subject; giant requests keep their own scale."""
    if not forced and not BUILDING.search(anchor) and not DWELLING.search(anchor):return '',NEGATIVE_PROMPT
    negative=NEGATIVE_PROMPT
    if not RUINED.search(anchor):negative+=', ruins, rubble, debris, broken fragments, crumbling walls'
    if DWELLING.search(anchor) and not FORTIFIED.search(anchor):negative+=', castle, fortress, battlements, turrets'
    # Wells, fountains, walls, bridges and statues have no door to measure a person against.
    enterable=DWELLING.search(anchor) or FORTIFIED.search(anchor) or ENTERABLE.search(anchor) or (forced and not OPEN_STRUCTURE.search(anchor))
    return ('' if GIANT.search(anchor) or not enterable else HUMAN_SCALE),negative
