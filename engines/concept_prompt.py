"""Image conditioning is separate from source text and evaluator instructions."""

NEGATIVE_PROMPT=('contact sheet, split screen, grid, collage, multiple views, turnaround, '
    'orthographic sheet, inset image, diagram, poster, decorative border, text, caption, watermark, logo, '
    'landscape, scenery, forest, clouds, sky, cropped, cut off, blurry, low quality, broken perspective')


def compose(description,style=''):
    # SDXL does not reliably understand negation. Put unwanted composition in the
    # negative conditioning rather than mentioning panels/scenery in the positive.
    return (description+('\nVisual style: '+style if style else '')+
        '\nA single standalone 3D game asset, zoomed out, three-quarter view, '
        'full object centered with clear margin, plain neutral studio background.'),NEGATIVE_PROMPT
