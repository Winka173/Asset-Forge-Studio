"""Image conditioning is separate from source text and evaluator instructions."""
import re

NEGATIVE_PROMPT=('contact sheet, split screen, grid, collage, multiple views, turnaround, '
    'orthographic sheet, inset image, diagram, poster, decorative border, text, caption, watermark, logo, '
    'landscape, scenery, forest, clouds, sky, cropped, cut off, blurry, low quality, broken perspective')

# Policy 3: description first, framing last (legacy; locked effective configs keep it).
# Policy 4: subject + framing + short style in the first CLIP window, then the complete description.
# Long prompts are encoded in 75-token windows and mean-pooled, so late anchors lose influence; nothing is dropped.
COMPOSITION_POLICY=4
FRAMING='single standalone 3D game asset, three-quarter view, full object centered with clear margin, plain neutral studio background'


def _clean(description):
    # SDXL does not reliably understand negation. Put unwanted composition in the
    # negative conditioning rather than mentioning panels/scenery in the positive.
    # Planning models occasionally restate forbidden layout keywords positively
    # inside a negated sentence. SDXL often renders those anyway. Move only known
    # composition exclusions; original prompt/translation remain immutable.
    description=re.sub(r'\bNo\s+(?:surrounding\s+)?(?:scenery|panels|poster layouts)[^.\n]*(?:\.|$)','',description,flags=re.I)
    return re.sub(r'\bInferred ordinary details include:\s*','',description,flags=re.I).strip()


def subject_anchor(description,max_words=24):
    """First sentence of the description, bounded so the anchor stays inside the first CLIP window."""
    first=re.split(r'(?<=[.!?])\s+|\n',description.strip(),maxsplit=1)[0]
    # Manifest headings carry markdown and stable IDs ('# BLD_CASTLE_T1 — CASTLE T1 Keep'); keep only the readable subject.
    first=re.sub(r'[#*_`>]+',' ',re.sub(r'\b[A-Z0-9]+(?:_[A-Za-z0-9]+)+\b',' ',first))
    first=re.sub(r'^[\s\W]+','',first)
    words=first.split()
    return ' '.join(words[:max_words]).rstrip(',;:.!?')


def short_style(style,max_words=18):
    return ' '.join(style.replace(';',',').split()[:max_words]).rstrip(',;:')


def compose(description,style='',quality=None,policy=COMPOSITION_POLICY):
    description=_clean(description)
    detail=('\nProduction game-asset beauty render, finely resolved surface relief, readable crafted edges, '
        'rich coherent material variation and carefully finished textures. Preserve the requested stylization.') if quality=='Maximum' else ''
    if policy==3:
        return (description+('\nVisual style: '+style if style else '')+detail+
            '\nA single standalone 3D game asset, zoomed out, three-quarter view, '
            'full object centered with clear margin, plain neutral studio background.'),NEGATIVE_PROMPT
    anchor=subject_anchor(description)
    head=f'{anchor}, {FRAMING}'+(f', {short_style(style)}' if style else '')+'.'
    return (head+'\n'+description+('\nVisual style: '+style if style else '')+detail),NEGATIVE_PROMPT
