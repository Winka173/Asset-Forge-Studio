"""Strict local manifest planner. Structured input or explicit line parser; no invented assets."""
import csv
import io
import json
import re
import hashlib
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

MAX_MANIFEST_CHARACTERS = 10_000_000
MAX_MANIFEST_ASSETS = 1000
ASSET_HEADING = re.compile(r'^# ([A-Z][A-Z0-9]*_[A-Za-z0-9_]+)[ \t]+[\u2014\u2013-][ \t]+([^\r\n]+)', re.MULTILINE)


class ManifestItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    asset_id: str = ''
    source_asset_id: str = ''
    source_status: str = Field(default='',max_length=200)
    source_line_start: int | None = Field(default=None,ge=1)
    source_line_end: int | None = Field(default=None,ge=1)
    source_char_start: int | None = Field(default=None,ge=0)
    source_char_end: int | None = Field(default=None,ge=0)
    source_sha256: str = ''
    semantic_metadata: dict = Field(default_factory=dict)
    name: str = Field(min_length=1,max_length=200)
    category: str = Field(default='',max_length=200)
    kind: Literal['auto','building','character','creature','prop','vehicle','nature'] = 'auto'
    # 2d: a transparent sprite (concept + cutout, no 3D); 3d: the 3D model pipeline.
    output: Literal['3d','2d'] = '3d'
    prompt: str = Field(default='',max_length=100000)
    style_constraints: dict = Field(default_factory=dict)
    target_width_m: float | None = Field(default=None,gt=0,le=1000)
    target_depth_m: float | None = Field(default=None,gt=0,le=1000)
    target_height_m: float | None = Field(default=None,gt=0,le=1000)
    expected_materials: list[str] = Field(default_factory=list,max_length=100)
    reference_ids: list[str] = Field(default_factory=list,max_length=50)
    dependencies: list[str] = Field(default_factory=list,max_length=100)
    asset_family: str = ''
    quality: Literal['Fast','Balanced','Maximum'] = 'Balanced'
    preferred_engine: Literal['auto','trellis2_community','triposg','hunyuan3d21'] = 'auto'
    engines: list[Literal['trellis2_community','triposg','hunyuan3d21']] = Field(default_factory=list,max_length=4)
    # Texturing for the shape engines (TripoSG, Hunyuan3D-2.1); empty = MV-Adapter, the tested default.
    texturer: Literal['','mvadapter','trellis2'] = ''
    candidates: int = Field(default=1,ge=1,le=5)
    # Optional game-ready triangle budget; the master keeps full detail and the delivered derivative is decimated to it.
    triangle_budget: int | None = Field(default=None,ge=500,le=5_000_000)
    # Generated concepts compared before image-to-3D; 0 = by quality (Maximum 3, Balanced 2, Fast 1).
    concept_candidates: int = Field(default=0,ge=0,le=6)
    # Longest-side cap for the game-ready derivative's textures (graphics target); the master keeps source maps.
    game_texture_size: Literal[1024,2048,4096] | None = None
    target_outputs: list[Literal['glb','fbx']] = Field(default=['glb'],min_length=1,max_length=2)
    selected: bool = True
    confirmed: bool = False
    priority: int = Field(default=0,ge=-1000,le=1000)
    skipped: bool = False


def expand(row):
    match=re.search(r'\bT(\d+)\s*[-–—]\s*T?(\d+)\b',row['name'],re.I)
    if not match:return [row]
    start,end=map(int,match.groups())
    if start>end or end-start>20:raise ValueError('Tier range phải tăng dần và không quá 21 tier')
    result=[]
    for tier in range(start,end+1):
        copy=dict(row);copy['asset_family']=copy.get('asset_family') or row['name'][:match.start()].strip()
        copy['name']=row['name'][:match.start()]+f'T{tier}'+row['name'][match.end():]
        # Shared constraints are explicit only; tier dimensions are never extrapolated.
        if end>start:
            for key in ('target_width_m','target_depth_m','target_height_m'):copy[key]=None
            copy['confirmed']=False
        result.append(copy)
    return result


def normalize(row):
    row=dict(row)
    if row.get('asset_id') and not row.get('source_asset_id') and 'id' not in row:row['source_asset_id']=row['asset_id']
    aliases={'id':'source_asset_id','width':'target_width_m','depth':'target_depth_m','height':'target_height_m',
             'width_m':'target_width_m','depth_m':'target_depth_m','height_m':'target_height_m','engine':'preferred_engine','family':'asset_family','materials':'expected_materials'}
    for old,new in aliases.items():
        if old in row:row[new]=row.pop(old)
    for key in ['expected_materials','reference_ids','dependencies','target_outputs']:
        if isinstance(row.get(key),str):
            raw=row[key].strip();row[key]=json.loads(raw) if raw.startswith('[') else [x.strip() for x in raw.split(';') if x.strip()]
    if isinstance(row.get('style_constraints'),str):row['style_constraints']=json.loads(row['style_constraints'] or '{}')
    for key in ['target_width_m','target_depth_m','target_height_m']:
        if row.get(key)=='':row[key]=None
    # CSV and table cells are text; empty optional numbers fall back to defaults.
    for key in ['triangle_budget','game_texture_size','candidates','concept_candidates','priority']:
        if isinstance(row.get(key),str):
            if not row[key].strip():row.pop(key)
            elif re.fullmatch(r'-?\d+',row[key].strip()):row[key]=int(row[key])
    for key in ['selected','confirmed','skipped']:
        if isinstance(row.get(key),str):row[key]=row[key].strip().lower() in ['true','1','yes']
    if 'project' in row:row.pop('project')  # project scope always comes from selected game.
    imported_status=row.pop('status',None)
    if imported_status and 'FUTURE' in str(imported_status).upper():row.setdefault('source_status','FUTURE')
    if str(row.get('source_asset_id','')).startswith('FUT_'):row.setdefault('source_status','FUTURE')
    # FUTURE is descriptive metadata; explicit user exclusions still win.
    row.pop('version',None)  # completion status is derived, never trusted from input.
    return row


def heading_prompts(text):
    """Long-form asset documents: split only ID headings, never internal Bible headings."""
    headings=list(ASSET_HEADING.finditer(text))
    rows=[]
    for index,heading in enumerate(headings):
        end=headings[index+1].start() if index+1<len(headings) else len(text)
        original=text[heading.start():end]
        body=text[heading.end():end]
        if not re.sub(r'[\s*#_`\-]','',body):raise ValueError(f'{heading[1]}: empty prompt body at line {text.count(chr(10),0,heading.start())+1}')
        future=heading[1].startswith('FUT_') or bool(re.search(r'\*\*STATUS:\s*FUTURE\b',original,re.I))
        row=dict(source_asset_id=heading[1],source_status='FUTURE' if future else 'PROPOSED',
                 name=heading[2].strip(),prompt=original,selected=True,confirmed=False,
                 source_line_start=text.count('\n',0,heading.start())+1,
                 source_line_end=text.count('\n',0,end-1)+1,
                 source_char_start=heading.start(),source_char_end=end,
                 source_sha256=hashlib.sha256(original.encode('utf-8')).hexdigest())
        # Explicit dimensions are proposed design estimates, never confirmed by importing.
        size=re.search(r'Target size:\s*\*\*([\d.]+)m wide \(X\)\s*[\u00d7x]\s*([\d.]+)m deep \(Z\)\s*[\u00d7x]\s*([\d.]+)m high \(Y\)',original)
        if size:row.update(zip(('target_width_m','target_depth_m','target_height_m'),map(float,size.groups())))
        rows.append(row)
    return rows


def detect_format(text):
    stripped=text.lstrip('\ufeff \t\r\n')
    if stripped.startswith(('[','{','```json')):return 'json'
    first=stripped.splitlines()[0] if stripped else ''
    if ',' in first and {'name','id','asset_id','source_asset_id'}.intersection(h.strip().lower() for h in first.split(',')):return 'csv'
    return 'markdown' if re.search(r'(?m)^\s*(?:#{1,6}\s|\||[-*+]\s|\d+[.)]\s)',stripped) else 'txt'


def diagnostics(text,fmt,rows,warnings):
    detected=detect_format(text)
    expected=re.search(r'ALL[ _-]+(\d+)[ _-]+(?:MODEL[ _-]+)?PROMPTS',text[:4096],re.I)
    future=sum(r.get('source_status')=='FUTURE' for r in rows)
    is_blocks=bool(ASSET_HEADING.search(text)) and (fmt in ('auto','markdown','txt'))
    warnings=list(warnings)
    if re.search(r'\b(?:Meshy|Tripo H3|paid batch)\b',text,re.I):warnings.append('External service names and budgets are retained as source requirements only. AFS uses local engines; no paid service is called and import does not verify those quality claims.')
    return dict(detected_format=detected,requested_format=fmt,parser_method='asset_id_heading_blocks' if is_blocks else 'strict_'+(detected if fmt=='auto' else fmt),
                local_ai_used=False,parsed_count=len(rows),expected_count=int(expected[1]) if expected else None,
                primary_count=len(rows)-future,future_count=future,status='Needs Review',warnings=list(warnings),errors=[])


def parse(text, fmt='auto'):
    stripped=text.strip();warnings=[]
    if not stripped:raise ValueError('Master Prompt/manifest trống')
    if len(text)>MAX_MANIFEST_CHARACTERS:raise ValueError(f'Manifest exceeds {MAX_MANIFEST_CHARACTERS:,} characters. Split the source file; input was not truncated.')
    if fmt=='auto':fmt=detect_format(text)
    if fmt=='json':
        raw=json.loads(re.sub(r'^```json\s*|\s*```$','',stripped))
        rows=raw if isinstance(raw,list) else raw.get('assets',raw.get('items'))
        if not isinstance(rows,list):raise ValueError('JSON cần array assets/items')
    elif fmt=='csv':
        rows=list(csv.DictReader(io.StringIO(stripped)))
    elif fmt in ('markdown','txt'):
        blocks=heading_prompts(text)
        lines=[x.strip() for x in stripped.splitlines() if x.strip()]
        table=[line for line in lines if line.startswith('|')]
        if blocks:
            rows=blocks
            warnings.append('Long-form Markdown: original asset IDs and complete prompt blocks preserved. FUTURE is a descriptive tag and remains eligible. Analyze creates no GPU jobs; estimated scale stays editable.')
        elif len(table)>=2:
            headers=[h.strip().lower().replace(' ','_') for h in table[0].strip('|').split('|')]
            rows=[dict(zip(headers,[v.strip() for v in line.strip('|').split('|')])) for line in table[1:] if not re.fullmatch(r'[|:\-\s]+',line)]
        else:
            rows=[]
            for line in lines:
                match=re.match(r'^(?:[-*+]\s+|\d+[.)]\s+)(.+)$',line)
                if not match:continue
                entry=match[1].strip().rstrip('.')
                if entry.lower().startswith(('một bộ modular ','a modular ')):
                    prefix=re.sub(r'^(một bộ modular|a modular)\s+','',entry,flags=re.I)
                    names=[x.strip() for x in re.split(r'\s*/\s*',prefix)]
                    rows.extend(dict(name=n,prompt=n,category='Modular',asset_family='Modular Wall/Gate') for n in names)
                else:
                    name,_,description=entry.partition(':')
                    rows.append(dict(name=name.strip(),prompt=description.strip() or name.strip()))
            warnings.append('Không có local LLM được cấu hình. Parser chỉ đọc danh sách/tier rõ ràng; hãy duyệt prompt và thông số từng asset. Văn xuôi không có danh sách cần chuyển thành JSON/CSV/Markdown.')
    else:raise ValueError('Định dạng chưa hỗ trợ')
    if not rows:raise ValueError('Không tìm thấy danh sách asset rõ ràng. Dùng bullet, Markdown table, JSON hoặc CSV; hệ thống không tự bịa asset.')
    if len(rows)>MAX_MANIFEST_ASSETS:raise ValueError(f'Manifest exceeds {MAX_MANIFEST_ASSETS} assets; split into smaller manifests for review.')
    result=[]
    for row in rows:
        normalized=normalize(row)
        for expanded in expand(normalized):result.append(ManifestItem.model_validate(expanded).model_dump())
        if len(result)>MAX_MANIFEST_ASSETS:raise ValueError(f'Expanded manifest exceeds {MAX_MANIFEST_ASSETS} assets.')
    names=[r['name'].casefold() for r in result]
    if len(set(names))!=len(names):raise ValueError('Tên asset bị trùng trong manifest')
    source_ids=[r['source_asset_id'] for r in result if r['source_asset_id']]
    if len(set(source_ids))!=len(source_ids):raise ValueError('Duplicate source asset IDs in manifest')
    expected=diagnostics(text,fmt,result,warnings)['expected_count']
    if expected is not None and expected!=len(result):raise ValueError(f'Source declares {expected} prompts but parser found {len(result)}. Check headings and delimiters; nothing was truncated.')
    for row in result:
        if not row['prompt'].strip():warnings.append(f'{row["name"]}: missing prompt body; fill it before generation. Original source is unchanged.')
        if not row['source_sha256']:row['source_sha256']=hashlib.sha256(row['prompt'].encode('utf-8')).hexdigest()
    return result,warnings
