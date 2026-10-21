"""Immutable delivery folders and project-scoped ZIPs over validated real outputs."""
import json
import re
import shutil
import threading
import zipfile
from pathlib import Path
from fastapi import HTTPException
from . import store

_lock=threading.RLock()


def slug(value):
    return re.sub(r'[^a-zA-Z0-9_-]+','-',value).strip('-')[:60] or 'asset'


def deliver(value,files):
    from . import studio
    asset=studio.asset(value['asset_id']);project=studio.project(asset['project_id'])
    # Names are descriptive; stable IDs keep renamed or identically named games apart.
    relative=f'exports/{slug(project["id"])}/{slug(asset["id"])}/{slug(value["id"])}'
    folder=store.safe_path(relative)
    archive_root=f'{slug(project["name"])}-{slug(project["id"])}/{slug(asset["name"])}-{asset["id"]}/{slug(value["preset"])}-{value["id"]}'
    with _lock:
        folder.mkdir(parents=True,exist_ok=True)
        manifest_file=folder/'export-manifest.json'
        if not manifest_file.exists():
            entries=[]
            for file in files:
                # All source paths originate in validated backend records, never a client path.
                source=Path(file['_source']).resolve()
                if not source.is_relative_to(store.DATA.resolve()) or not source.is_file():raise HTTPException(409,'Validated export source is missing')
                name=Path(file['name']).as_posix()
                if name.startswith('/') or '..' in Path(name).parts or ':' in name:raise HTTPException(409,'Unsafe export filename')
                target=(folder/name).resolve()
                if not target.is_relative_to(folder.resolve()):raise HTTPException(409,'Export path escapes project directory')
                target.parent.mkdir(parents=True,exist_ok=True);checksum=store.digest(source)
                if target.exists():
                    if store.digest(target)!=checksum:raise HTTPException(409,'Immutable export output changed')
                else:
                    temporary=target.with_name(target.name+'.part');shutil.copyfile(source,temporary)
                    if store.digest(temporary)!=checksum:raise HTTPException(409,'Export copy checksum failed')
                    temporary.replace(target)
                entries.append(dict(name=name,bytes=target.stat().st_size,sha256=checksum))
            manifest=dict(schema_version='1.0',export_id=value['id'],project_id=project['id'],project_name=project['name'],asset_id=asset['id'],asset_name=asset['name'],
                source_artifact_id=value['artifact_id'],preset=value['preset'],format=value['format'],files=entries,archive_root=archive_root,
                quality='Same validated source bytes; no new inference or artistic approval',created_at=value['created_at'])
            temporary=manifest_file.with_suffix('.json.part');temporary.write_text(json.dumps(manifest,indent=2),encoding='utf-8');temporary.replace(manifest_file)
        manifest=json.loads(manifest_file.read_text(encoding='utf-8'))
        bundle_name=f'{slug(manifest["project_name"])}-{slug(project["id"])[:8]}-{slug(manifest["asset_name"])}-{slug(value["preset"])}.zip'
        bundle=folder/bundle_name
        if not bundle.exists():
            temporary=bundle.with_suffix('.zip.part')
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED) as archive:
                for file in manifest['files']:archive.write(folder/file['name'],manifest['archive_root']+'/'+file['name'])
                archive.write(manifest_file,manifest['archive_root']+'/export-manifest.json')
            temporary.replace(bundle)
        base=f'/api/exports/{value["id"]}/files/'
        value.update(project_id=project['id'],export_directory=str(folder),archive_root=manifest['archive_root'],
            files=[dict(name=bundle.name,bytes=bundle.stat().st_size,url=base+bundle.name,kind='project_bundle')]+[
                dict(name=file['name'],bytes=file['bytes'],sha256=file['sha256'],url=base+file['name']) for file in manifest['files']])
    return value


def download(identifier,name):
    from . import studio
    with store.connect() as db:row=db.execute('SELECT payload FROM asset_exports WHERE id=?',(identifier,)).fetchone()
    if not row:raise HTTPException(404,'Export not found')
    value=dict(id=identifier,**json.loads(row['payload']))
    result=studio.output_files(value)
    match=next((f for f in result.get('files',[]) if f['name']==name),None)
    if not match:raise HTTPException(404,'Export file is not a completed output')
    path=(Path(result['export_directory'])/name).resolve();folder=Path(result['export_directory']).resolve()
    if not path.is_relative_to(folder) or not path.is_file():raise HTTPException(404,'Export file missing')
    if match.get('sha256') and store.digest(path)!=match['sha256']:raise HTTPException(409,'Export checksum changed')
    return path
