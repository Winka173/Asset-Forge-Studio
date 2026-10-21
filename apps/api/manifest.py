"""Strict local manifest planner. Structured input or explicit line parser; no invented assets."""
import csv
import io
import json
import re
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ManifestItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    asset_id: str = ''
    source_asset_id: str = ''
    name: str = Field(min_length=1,max_length=200)
    category: str = Field(default='',max_length=200)
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
    preferred_engine: Literal['auto','triposg','trellis2_community'] = 'auto'
    candidates: int = Field(default=1,ge=1,le=4)
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
    for key in ['selected','confirmed','skipped']:
        if isinstance(row.get(key),str):row[key]=row[key].strip().lower() in ['true','1','yes']
    if 'project' in row:row.pop('project')  # project scope always comes from selected game.
    row.pop('status',None);row.pop('version',None)  # derived, never trusted from imported completion labels.
    return row


def parse(text, fmt='auto'):
    stripped=text.strip();warnings=[]
    if not stripped:raise ValueError('Master Prompt/manifest trống')
    if fmt=='auto':fmt='json' if stripped.startswith(('[','{','```json')) else 'csv' if re.match(r'(?i)(name|id|asset_id),',stripped) else 'markdown'
    if fmt=='json':
        raw=json.loads(re.sub(r'^```json\s*|\s*```$','',stripped))
        rows=raw if isinstance(raw,list) else raw.get('assets',raw.get('items'))
        if not isinstance(rows,list):raise ValueError('JSON cần array assets/items')
    elif fmt=='csv':
        rows=list(csv.DictReader(io.StringIO(stripped)))
    elif fmt=='markdown':
        lines=[x.strip() for x in stripped.splitlines() if x.strip()]
        table=[line for line in lines if line.startswith('|')]
        if len(table)>=2:
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
    if len(rows)>200:raise ValueError('Manifest lớn hơn 200 dòng: chia batch nhỏ để duyệt')
    result=[]
    for row in rows:
        normalized=normalize(row)
        for expanded in expand(normalized):result.append(ManifestItem.model_validate(expanded).model_dump())
    names=[r['name'].casefold() for r in result]
    if len(set(names))!=len(names):raise ValueError('Tên asset bị trùng trong manifest')
    return result,warnings
