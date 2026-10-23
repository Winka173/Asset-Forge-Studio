"""Image conditioning is separate from source text and evaluator instructions."""
import re

NEGATIVE_PROMPT=('contact sheet, split screen, grid, collage, multiple views, turnaround, '
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
COMPOSITION_POLICY=6
CONDITIONING_WORDS=160
FRAMING='single standalone 3D game asset, three-quarter view, full object centered with clear margin, plain neutral studio background'


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


def compose(description,style='',quality=None,policy=COMPOSITION_POLICY,directives=()):
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
    head=f'{anchor}, {FRAMING}'+(f', {short_style(style)}' if style else '')+'.'
    return (head+'\n'+description+('\nVisual style: '+style if style else '')+detail),NEGATIVE_PROMPT
