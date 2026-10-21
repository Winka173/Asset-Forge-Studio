"""Hash-bound prompt requirements and measured checks, never invented visual approval."""
import hashlib
import json
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from . import store, studio

router = APIRouter(prefix='/api/production')
VERSION = '1.0'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def extract(prompt):
    """Conservative explicit excerpts; unsupported natural language remains in original text."""
    found = []
    def add(kind, match, **data):
        excerpt = prompt[match.start():match.end()]
        record = dict(kind=kind, excerpt=excerpt, source_start=match.start(), source_end=match.end(), **data)
        record['id'] = digest(record)[:16]
        if record['id'] not in {v['id'] for v in found}:found.append(record)
    for match in re.finditer(r'\b(height|width|depth)\s*(?:(?:of|is|to)\s*|[:=]\s*)?(\d+(?:\.\d+)?)\s*(cm|meters?|metres?|m)\b',prompt,re.I):
        add('dimension',match,axis={'width':0,'height':1,'depth':2}[match[1].lower()],target_m=float(match[2])*(.01 if match[3].lower()=='cm' else 1))
    # Explicit mentions, not inferred counts, presence, or positive/negative requirements.
    for match in re.finditer(r'\b(ballista|battlements?|crenellations?|balcon(?:y|ies)|staircase|drawbridge|archer tower|watchtower)\b',prompt,re.I):
        add('component_mention',match,verification='Visual presence/absence and negation require inspection')
    for match in re.finditer(r'\b(?:(?:blue|red|green|golden|black|white|purple|orange)\s+(?:roof|rooftop|crystal|stone|wood)|(?:roof|rooftop)\s*(?:is|:|=)\s*(?:blue|red|green|golden|black|white|purple|orange))\b',prompt,re.I):
        add('color_mention',match,verification='Material names and average texture colors do not prove this requirement')
    for match in re.finditer(r'\b(stone|wooden|metal|crystal|stylized|hand-painted|isometric)\b',prompt,re.I):
        add('appearance_mention',match,verification='Visual inspection required')
    for axis in range(3):
        declarations=[r for r in found if r['kind']=='dimension' and r['axis']==axis]
        for earlier in declarations[:-1]:earlier['superseded_by']=declarations[-1]['id']
    return found


def context(asset_id,artifact_id=None):
    model=studio.asset(asset_id)
    record=studio.scoped_artifact(artifact_id,model['project_id'],asset_id) if artifact_id else None
    if record and record['role']!='candidate':raise HTTPException(400,'Select a real model candidate')
    revision_id=None
    if record and record['metadata'].get('job_id'):
        from . import jobs
        try:revision_id=jobs.get(record['metadata']['job_id'])['payload'].get('revision_id')
        except KeyError:pass
    revision=next((r for r in model.get('revisions',[]) if artifact_id and r.get('artifact_id')==artifact_id or revision_id and r['id']==revision_id),None)
    prompt=revision['effective_prompt'] if revision else model.get('original_prompt',model.get('prompt',''))
    requirements=extract(prompt)
    contract=dict(schema_version=VERSION,asset_id=asset_id,artifact_id=artifact_id,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),source='effective_revision_prompt' if revision else 'immutable_original_prompt',requirements=requirements,
                  coverage='Conservative English explicit dimensions and selected component/color/style mentions; not exhaustive semantic parsing')
    contract['contract_hash']=digest(contract)
    return model,record,contract


def evaluate(asset_id,artifact_id,measurements=None):
    model,record,contract=context(asset_id,artifact_id)
    path=store.safe_path(record['relative_path'])
    if store.digest(path)!=record['sha256']:raise HTTPException(409,'Model bytes changed; no requirement report accepted')
    if measurements is None:
        from .inspection import inspect_glb
        measurements=inspect_glb(path)
    dimensions=measurements['dimensions_xyz_m']
    checks=[]
    for requirement in contract['requirements']:
        check=dict(requirement_id=requirement['id'],status='not_evaluated',method='visual_evaluator_unavailable',evidence=None)
        if requirement.get('superseded_by'):check.update(status='superseded',method='later_explicit_dimension')
        elif requirement['kind']=='dimension':
            expected=requirement['target_m'];actual=dimensions[requirement['axis']];tolerance=max(.001,expected*.01)
            check.update(status='passed' if abs(actual-expected)<=tolerance else 'mismatch',method='measured_glb_world_bounds',evidence=dict(expected_m=expected,actual_m=actual,tolerance_m=tolerance))
        checks.append(check)
    report=dict(schema_version=VERSION,asset_id=asset_id,artifact_id=artifact_id,artifact_sha256=record['sha256'],contract=contract,checks=checks,report_id=digest(dict(contract=contract['contract_hash'],artifact_sha256=record['sha256'],version=VERSION)),
                evaluated_at=store.now(),visual_evaluation='unavailable',artistic_approval=False,summary=dict(measured=sum(c['method']=='measured_glb_world_bounds' for c in checks),mismatches=sum(c['status']=='mismatch' for c in checks),unverified=sum(c['status']=='not_evaluated' for c in checks)),
                policy='Informational checks; existing technical QA and review/export policies remain authoritative. Visual unknowns do not block Auto.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=json.loads(db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone()['payload'])
        reports=current.setdefault('fidelity_reports',[])
        existing=next((r for r in reports if r['report_id']==report['report_id']),None)
        if existing:return existing
        reports.append(report)
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(current),asset_id))
    return report


@router.get('/assets/{asset_id}/requirements')
def requirements(asset_id:str,artifact_id:str|None=None):
    model,record,contract=context(asset_id,artifact_id)
    report=next((r for r in reversed(model.get('fidelity_reports',[])) if r['contract']['contract_hash']==contract['contract_hash'] and record and r['artifact_sha256']==record['sha256']),None)
    return dict(contract=contract,report=report,visual_evaluator=dict(available=False,reason='No locally validated visual requirement evaluator is configured. No paid fallback or weight download.'))


class Evaluation(BaseModel):
    artifact_id:str=Field(min_length=1,max_length=100)


@router.post('/assets/{asset_id}/requirements/evaluate')
def evaluate_route(asset_id:str,body:Evaluation):return evaluate(asset_id,body.artifact_id)
