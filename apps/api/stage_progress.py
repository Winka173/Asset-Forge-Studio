"""Chronological progress from actual subprocess records; never estimates pipeline time."""
import re


def parse(tail,status):
    value=dict(stage=status,percent=None,scope='current_stage_only')
    for line in re.split(r'[\r\n]',tail):
        line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line)
        if line.startswith('STAGE '):
            value.update(stage=line.removeprefix('STAGE ').strip(),percent=None)
            continue
        for progress in re.finditer(r'([^\r\n:\[\]]+):\s*(\d+)%\|',line):
            percent=int(progress[2])
            if 0<=percent<=100:value.update(stage=progress[1].strip(),percent=percent)
        frame=re.search(r'AFS_FRAME (\d+)/(\d+)',line)
        if frame and not value['stage'].lower().startswith('encode'):
            done,total=map(int,frame.groups())
            if total>0 and 0<=done<=total:value.update(stage=f'Blender frames {done}/{total}',percent=100*done/total)
    return value
