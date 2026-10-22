"""Measured image palette, not an image editing or semantic style-transfer model."""
import re
from PIL import Image
from . import store,studio


def concept_direction(prompt,reference_ids,project_id):
    colors=[];records=[]
    names={(0,0,0):'charcoal',(0,0,1):'navy blue',(0,0,2):'blue',(0,1,0):'dark green',
           (0,1,1):'teal',(0,1,2):'cyan',(1,0,0):'brown',(1,1,0):'ochre',
           (1,1,1):'gray',(2,1,0):'gold',(2,1,1):'terracotta',(2,2,1):'ivory',(2,2,2):'white'}
    for identifier in reference_ids:
        record=studio.scoped_artifact(identifier,project_id)
        if record['role'] not in ('reference','concept'):raise ValueError('Style direction requires an image')
        path=store.safe_path(record['relative_path'])
        if store.digest(path)!=record['sha256']:raise ValueError('Style reference checksum changed')
        with Image.open(path) as image:
            image=image.convert('RGBA');image.thumbnail((128,128))
            pixels=[p[:3] for p in image.getdata() if p[3]>128 and not(min(p[:3])>235)]
        if not pixels:raise ValueError('Reference contains no visible non-background palette')
        palette=Image.new('RGB',(len(pixels),1));palette.putdata(pixels)
        quantized=palette.quantize(colors=5);rgb=quantized.getpalette()
        measured=[]
        for count,index in sorted(quantized.getcolors(),reverse=True):
            color=rgb[index*3:index*3+3];key=tuple(min(2,int(c)//86) for c in color)
            label=names.get(key,'muted mixed color');colors.append(label)
            measured.append(dict(rgb=color,pixels=count,label=label))
        records.append(dict(artifact_id=identifier,sha256=record['sha256'],palette=measured))
    # Explainable bilingual hints for common architecture nouns; not a translation model.
    hints=[english for expression,english in [(r'lâu\s+đài','castle, broad fortified complex, enclosing walls and multiple towers'),(r'tháp\s+canh','watchtower')]
           if re.search(expression,prompt,re.I)]
    suffix=('\nSubject: '+ '; '.join(hints)) if hints else ''
    if records:suffix+='\nColors: '+', '.join(dict.fromkeys(colors))+'.'
    return prompt+suffix,dict(method='measured_palette_only',references=records,bilingual_noun_hints=hints,
        limitations='No image-semantic style transfer, material recognition or verified prompt fidelity. Original prompt is retained.')
