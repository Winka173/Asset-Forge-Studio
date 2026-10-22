"""Durable inbox projected from actual job transitions and delivered export records."""
import hashlib
import json
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel,Field
from . import store

router=APIRouter(prefix='/api/notifications')


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS production_notifications (id TEXT PRIMARY KEY,project_id TEXT NOT NULL,asset_id TEXT,kind TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,read_at TEXT,cleared_at TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS production_notification_cursor (id TEXT PRIMARY KEY,at TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS notifications_project_time ON production_notifications(project_id,created_at)')


def sync():
    # One transaction binds event ingestion and read/clear state. Repeated polling
    # inserts the same stable IDs, never re-creates cleared or read notifications.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        projects={r['id']:json.loads(r['payload']).get('name',r['id']) for r in db.execute('SELECT id,payload FROM projects')}
        assets={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM assets')}
        targets={}
        def target(asset_id,batch_id=None):
            if batch_id:
                row=db.execute('SELECT payload FROM batches WHERE id=?',(batch_id,)).fetchone()
                parent=json.loads(row['payload']).get('revision_of') if row else None
                return (parent or batch_id)+'/'+asset_id
            if asset_id not in targets:
                row=db.execute("SELECT id FROM jobs WHERE json_extract(payload,'$.asset_id')=? AND json_extract(payload,'$.batch_id') IS NULL ORDER BY created_at LIMIT 1",(asset_id,)).fetchone()
                targets[asset_id]='job/'+row['id'] if row else ''
            return targets[asset_id]
        def record(identity,project_id,asset_id,kind,title,message,at,link):
            if project_id not in projects:return
            identifier=hashlib.sha256(identity.encode()).hexdigest()
            payload=dict(id=identifier,project_id=project_id,project_name=projects[project_id],asset_id=asset_id,asset_name=assets.get(asset_id,{}).get('name',asset_id),kind=kind,title=title,message=message,created_at=at,target=link)
            db.execute('INSERT OR IGNORE INTO production_notifications VALUES (?,?,?,?,?,?,NULL,NULL)',(identifier,project_id,asset_id,kind,json.dumps(payload),at))
        cursor=db.execute("SELECT at FROM production_notification_cursor WHERE id='jobs'").fetchone()
        since=cursor['at'] if cursor else ''
        stamp=store.now()
        for row in db.execute("SELECT * FROM jobs WHERE updated_at>=? AND status IN ('REVIEW_REQUIRED','FAILED','BLOCKED')",(since,)).fetchall():
            payload=json.loads(row['payload']);asset_id=payload.get('asset_id');project_id=payload.get('project_id')
            if not asset_id or not project_id:continue
            success=row['status']=='REVIEW_REQUIRED';kind=payload.get('kind','stage')
            label={'concept':'Concept image','inference':'3D candidate','blender':'Blender processing and technical QA','world_unity':'Unity world build','fx_unity':'Unity effect build','unity_import':'Unity import'}.get(kind,kind)
            message='Stage finished. Artistic review remains independent.' if success else (row['error'] or 'Open the pipeline to inspect the failed or blocked stage.')
            record('job:'+row['id']+':'+row['status']+':'+row['updated_at'],project_id,asset_id,'completed' if success else 'failed',label+(' completed' if success else ' needs attention'),message,row['updated_at'],target(asset_id,payload.get('batch_id')))
        db.execute('INSERT OR REPLACE INTO production_notification_cursor VALUES (?,?)',('jobs',stamp))
        tables={r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'selective_exports' in tables:
            for row in db.execute('SELECT * FROM selective_exports').fetchall():
                value=json.loads(row['payload'])
                if value.get('status')!='COMPLETED':continue
                asset_id=value['asset_id'];model=assets.get(asset_id,{})
                job=db.execute("SELECT payload FROM jobs WHERE json_extract(payload,'$.asset_id')=? ORDER BY created_at DESC LIMIT 1",(asset_id,)).fetchone()
                batch_id=json.loads(job['payload']).get('batch_id') if job else None
                staged=value.get('delivery_scope')=='staged'
                record('export:'+row['id'],model.get('project_id'),asset_id,'completed','Revision files prepared' if staged else 'Asset exported',('Revision saved separately; the game-facing version was preserved.' if staged else 'Validated export recorded: '+value.get('filename',''))+' No artistic approval is implied.',value.get('created_at') or stamp,target(asset_id,batch_id))


@router.get('')
def listing(project_id:str|None=None,kind:Literal['all','completed','failed']='all',unread:bool=False,limit:int=100,offset:int=0):
    sync()
    with store.connect() as db:
        conditions=['cleared_at IS NULL'];args=[]
        if project_id:conditions.append('project_id=?');args.append(project_id)
        unread_count=db.execute('SELECT COUNT(*) FROM production_notifications WHERE '+' AND '.join(conditions+['read_at IS NULL']),args).fetchone()[0]
        if kind!='all':conditions.append('kind=?');args.append(kind)
        if unread:conditions.append('read_at IS NULL')
        where=' AND '.join(conditions)
        total=db.execute('SELECT COUNT(*) FROM production_notifications WHERE '+where,args).fetchone()[0]
        rows=db.execute('SELECT * FROM production_notifications WHERE '+where+' ORDER BY created_at DESC,id LIMIT ? OFFSET ?',(*args,max(1,min(limit,200)),max(0,offset))).fetchall()
    return dict(items=[json.loads(row['payload'])|dict(read=row['read_at'] is not None) for row in rows],unread_count=unread_count,total=total,has_more=max(0,offset)+len(rows)<total,next_offset=max(0,offset)+len(rows))


class Selection(BaseModel):
    ids:list[str]=Field(default_factory=list,max_length=1000)
    all:bool=False
    project_id:str|None=None


def mark(body:Selection,field:str):
    sync()
    conditions=['cleared_at IS NULL'];args=[]
    if body.project_id:conditions.append('project_id=?');args.append(body.project_id)
    if not body.all:
        if not body.ids:return dict(updated=0)
        conditions.append('id IN ('+','.join('?' for _ in body.ids)+')');args.extend(body.ids)
    with store.connect() as db:
        result=db.execute('UPDATE production_notifications SET '+field+'=? WHERE '+' AND '.join(conditions),(store.now(),*args))
    return dict(updated=result.rowcount)


@router.post('/read')
def read(body:Selection):return mark(body,'read_at')


@router.post('/clear')
def clear(body:Selection):return mark(body,'cleared_at')
