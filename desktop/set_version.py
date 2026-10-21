"""Bump AFS release fields without touching dependency package versions."""
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def set_version(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Expected major.minor.patch')
    for relative in ('package.json','package-lock.json','src-tauri/tauri.conf.json'):
        file=ROOT/relative;value=json.loads(file.read_text(encoding='utf-8'))
        value['version']=version
        if relative=='package-lock.json':value['packages']['']['version']=version
        file.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    file=ROOT/'src-tauri/Cargo.toml';text=file.read_text(encoding='utf-8')
    text=re.sub(r'(?m)^version = "[^"]+"','version = "'+version+'"',text,count=1);file.write_text(text,encoding='utf-8')
    file=ROOT/'src-tauri/Cargo.lock';text=file.read_text(encoding='utf-8')
    text=re.sub(r'(name = "asset-forge-studio"\nversion = ")[^"]+',lambda m:m[1]+version,text,count=1);file.write_text(text,encoding='utf-8')
    file=ROOT/'apps/api/main.py';text=file.read_text(encoding='utf-8')
    text=re.sub(r'(FastAPI\(title="Asset Forge Studio", version=")[^"]+',lambda m:m[1]+version,text,count=1);file.write_text(text,encoding='utf-8')

if __name__=='__main__':set_version(sys.argv[1])
