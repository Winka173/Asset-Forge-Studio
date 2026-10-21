"""Explicit developer-only download of the licensed glTF viewer fixture, never app startup."""
import hashlib
import json
import urllib.request
from pathlib import Path

BASE='https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Models/main/2.0/RiggedSimple/'
EXPECTED='3a79dabb67bb0cd598a18d08b954d9d357c27c30672f82ef5d3f4e7fe6ca3401'

def fetch():
    folder=Path(__file__).resolve().parents[1]/'.local/fixtures';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'RiggedSimple.glb'
    if target.exists():data=target.read_bytes()
    else:
        with urllib.request.urlopen(BASE+'glTF-Binary/RiggedSimple.glb',timeout=60) as response:data=response.read(1_000_001)
    if len(data)>1_000_000 or data[:4]!=b'glTF' or hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Fixture changed; review upstream bytes and license before replacing the pinned source')
    if not target.exists():
        temporary=target.with_suffix('.glb.part');temporary.write_bytes(data);temporary.replace(target)
    notice=dict(name='Rigged Simple',creator='Cesium, donated for glTF testing',source=BASE+'glTF-Binary/RiggedSimple.glb',license='CC BY 4.0',license_url='https://creativecommons.org/licenses/by/4.0/',readme=BASE+'README.md',sha256=EXPECTED,scope='Technical animation/skin viewer test; not generated character quality, auto-rig or retarget evidence')
    (folder/'RiggedSimple.NOTICE.json').write_text(json.dumps(notice,indent=2),encoding='utf-8')
    print(json.dumps(dict(path=str(target),bytes=len(data),sha256=EXPECTED,license='CC BY 4.0')))

if __name__=='__main__':fetch()
