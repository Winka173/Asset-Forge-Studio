"""Reusable style profile from an approved reference: materials, colours and rendering style, never its shape.

Image-prompt conditioning (IP-Adapter) also transfers silhouette cues: a watchtower anchor gave trees doors and
fountains spires. The profile keeps only transferable style as text plus a measured palette for ranking.
"""
import colorsys
import json
import re
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image
from . import intent_adapter, local_semantics

POLICY_VERSION = 1
# Words that describe structure or parts of the reference object; they must never reach other assets' prompts.
SHAPE_WORDS = re.compile(r'\b(?:towers?|turrets?|spires?|roofs?|rooftops?|roofing|domes?|chimneys?|doors?|doorways?|windows?|walls?|gates?|'
                         r'balcon(?:y|ies)|battlements?|crenellations?|stairs?|staircases?|steps?|columns?|pillars?|arch(?:es|way)?|'
                         r'buildings?|castles?|houses?|keeps?|fortress(?:es)?|platforms?|pedestals?|bases?|foundations?|finials?|beams?|'
                         r'shingles?|tiles?|banners?|flags?|gargoyles?|structures?|architectur\w*)\b', re.I)


class Material(BaseModel):
    model_config = ConfigDict(extra='forbid')
    substance: str = Field(min_length=1, max_length=60)
    colour: str = Field(min_length=1, max_length=40)
    finish: Literal['matte', 'satin', 'glossy', 'metallic', 'emissive']
    wear: Literal['clean', 'light_wear', 'weathered', 'heavily_worn']


class StyleObservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rendering_style: str = Field(min_length=1, max_length=120)
    stylization: Literal['realistic', 'semi_stylized', 'stylized', 'toon']
    materials: list[Material] = Field(min_length=1, max_length=6)
    surface_detail: Literal['low', 'medium', 'high']
    edge_treatment: str = Field(min_length=1, max_length=100)
    accent: str = Field(default='', max_length=100)


def clean(text):
    """Remove structural vocabulary; keep substances and colours ('navy slate roof tiles' -> 'navy slate')."""
    return re.sub(r'\s{2,}', ' ', re.sub(r'\s+([,;.])', r'\1', SHAPE_WORDS.sub('', text))).strip(' ,;.-')


def colour_name(rgb):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    warm = rgb[0] > rgb[2] + 10
    if s < 0.12 or l < 0.08 or l > 0.94:
        return 'near black' if l < 0.15 else 'charcoal grey' if l < 0.35 else ('warm grey' if warm else 'grey') if l < 0.65 else 'ivory' if warm else 'off-white'
    if s < 0.35 and 15 <= h * 360 < 70:  # muted warm tones read as stone/sand, not orange
        return 'cream' if l > 0.7 else 'sand beige' if l > 0.5 else 'brown' if s >= 0.2 and l < 0.45 else 'taupe' if l > 0.3 else 'dark brown'
    if s < 0.35 and 190 <= h * 360 < 260:
        return 'slate blue' if l < 0.45 else 'blue grey'
    hues = [(15, 'red'), (40, 'orange'), (55, 'amber'), (70, 'yellow'), (160, 'green'), (180, 'teal'), (205, 'cyan'), (250, 'blue'), (290, 'violet'), (335, 'magenta'), (360, 'red')]
    name = next(n for limit, n in hues if h * 360 < limit)
    if name in ('orange', 'amber') and l < 0.45: name = 'brown' if s < 0.6 else 'bronze'
    if name == 'blue' and l < 0.35: name = 'navy blue'
    tone = 'dark ' if l < 0.3 and name not in ('navy blue', 'brown') else 'pale ' if l > 0.75 else ''
    return tone + name


def measure_palette(path, colours=6):
    """Measured subject palette (background excluded by distance to the corner colour); deterministic."""
    with Image.open(path) as source:
        image = source.convert('RGB'); image.thumbnail((256, 256))
    pixels = list(image.getdata()); w, h = image.size
    corners = [image.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    background = tuple(sorted(c[i] for c in corners)[1] for i in range(3))
    subject = [p for p in pixels if sum((a - b) ** 2 for a, b in zip(p, background)) > 900] or pixels
    strip = Image.new('RGB', (len(subject), 1)); strip.putdata(subject)
    quantized = strip.quantize(colors=colours, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()[:colours * 3]; counts = sorted(quantized.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    entries = [dict(hex='#%02x%02x%02x' % tuple(palette[i * 3:i * 3 + 3]), share=round(c / total, 4), name=colour_name(palette[i * 3:i * 3 + 3])) for c, i in counts]
    saturation = sum(colorsys.rgb_to_hls(*(v / 255 for v in p))[2] for p in subject) / len(subject)
    return dict(entries=entries, mean_saturation=round(saturation, 4), subject_fraction=round(len(subject) / len(pixels), 4))


def observe(path, progress=lambda message: None):
    """Local Qwen3-VL observation of transferable style; a schema without shape fields plus vocabulary cleaning."""
    selected = intent_adapter.model(); started = time.monotonic(); progress('Analyze style reference / Qwen3-VL / CPU')
    system = ('Describe ONLY the reusable visual style of this reference image so it can be applied to OTHER objects with completely '
              'different shapes (trees, weapons, potions, characters, props). Report materials by substance and colour, surface finish, '
              'wear, edge treatment and rendering style. Never mention what the object is, its shape, structure, parts, proportions or '
              'layout: no towers, roofs, doors, windows, walls, stairs, bases or buildings. Name materials by substance only, for example '
              '"ivory limestone", "midnight blue slate", "aged bronze", "chestnut oak".')
    response = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=StyleObservation.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=8192, num_predict=700, num_gpu=0, num_thread=8),
        messages=[dict(role='system', content=system), dict(role='user', content='Describe the transferable style.', images=[intent_adapter.image_input(path)])]), timeout=600)
    if not response.get('done') or response.get('done_reason') == 'length': raise ValueError('Style reference response incomplete')
    observation = StyleObservation.model_validate_json(response['message']['content'])
    return dict(observation=observation.model_dump(), model=selected['name'], model_digest=selected['digest'], duration_seconds=round(time.monotonic() - started, 2))


def style_text(profile, max_materials=5):
    """Short, shape-free style description for concept conditioning."""
    palette = ', '.join(dict.fromkeys(e['name'] for e in profile['palette']['entries'] if e['share'] >= 0.04))
    observed = (profile.get('observed') or {}).get('observation')
    if not observed:
        return f'colour palette: {palette}' if palette else ''
    def material(m):
        substance = m['substance'].split(); colour = [w for w in m['colour'].split() if w.lower() not in {s.lower() for s in substance}]
        return clean(' '.join(colour + substance)) + f" ({m['finish']}{', ' + m['wear'].replace('_', ' ') if m['wear'] != 'clean' else ''})"
    materials = [material(m) for m in observed['materials'][:max_materials]]
    parts = [clean(observed['rendering_style']), observed['stylization'].replace('_', '-'), 'materials: ' + ', '.join(m for m in materials if not m.startswith('(')),
             clean(observed['edge_treatment']), f"{observed['surface_detail']} surface detail", clean(observed.get('accent', '')), f'colour palette: {palette}' if palette else '']
    return '; '.join(p for p in parts if p)


def fingerprint(profile):
    import hashlib
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
