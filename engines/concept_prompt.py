"""Image conditioning is separate from source text and evaluator instructions."""
import re

NEGATIVE_PROMPT=('contact sheet, split screen, grid, collage, multiple views, turnaround, '
    'orthographic sheet, inset image, diagram, poster, decorative border, text, caption, watermark, logo, '
    'landscape, scenery, forest, clouds, sky, cropped, cut off, blurry, low quality, broken perspective')


def compose(description,style='',quality=None):
    # SDXL does not reliably understand negation. Put unwanted composition in the
    # negative conditioning rather than mentioning panels/scenery in the positive.
    # Planning models occasionally restate forbidden layout keywords positively
    # inside a negated sentence. SDXL often renders those anyway. Move only known
    # composition exclusions; original prompt/translation remain immutable.
    description=re.sub(r'\bNo\s+(?:surrounding\s+)?(?:scenery|panels|poster layouts)[^.\n]*(?:\.|$)','',description,flags=re.I)
    description=re.sub(r'\bInferred ordinary details include:\s*','',description,flags=re.I)
    detail=('\nProduction game-asset beauty render, finely resolved surface relief, readable crafted edges, '
        'rich coherent material variation and carefully finished textures. Preserve the requested stylization.') if quality=='Maximum' else ''
    return (description+('\nVisual style: '+style if style else '')+detail+
        '\nA single standalone 3D game asset, zoomed out, three-quarter view, '
        'full object centered with clear margin, plain neutral studio background.'),NEGATIVE_PROMPT
