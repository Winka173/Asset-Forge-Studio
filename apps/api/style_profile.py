"""Project style profile: analyze the approved style anchor once (CPU), then condition concepts on its text only.

Mode 'profile' (default) keeps the anchor image out of SDXL, so its silhouette never transfers; the anchor still
scores palette similarity in the concept tournament. Mode 'image' keeps the earlier IP-Adapter conditioning.
"""
import json
from . import store, jobs

IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')


def anchor(project_id, project, style_reference_ids=()):
    """The approved style image for this request (first explicit style reference, else the project anchor)."""
    anchor_id = next(iter(style_reference_ids or ()), None) or project.get('style_anchor_artifact_id')
    if not anchor_id: return None
    from .studio import scoped_artifact
    record = scoped_artifact(anchor_id, project_id)
    path = store.safe_path(record['relative_path'])
    if path.suffix.lower() not in IMAGE_SUFFIXES or store.digest(path) != record['sha256']: return None
    return dict(record=record, path=path)


def mode(project):
    return project.get('style_anchor_mode') or 'profile'


def find(project_id, anchor_sha256):
    from engines.style_profile import POLICY_VERSION
    with store.connect() as db:
        rows = db.execute("SELECT id FROM artifacts WHERE role='style_profile' AND project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    for row in rows:
        record = store.get_artifact(row['id']); meta = record['metadata']
        if meta.get('project_id') == project_id and meta.get('anchor_sha256') == anchor_sha256 and meta.get('policy_version') == POLICY_VERSION:
            path = store.safe_path(record['relative_path'])
            if store.digest(path) == record['sha256']: return json.loads(path.read_text(encoding='utf-8')) | dict(artifact_id=record['id'], sha256=record['sha256'])
    return None


def measured_only(source):
    from engines.style_profile import measure_palette, POLICY_VERSION
    return dict(policy_version=POLICY_VERSION, anchor_artifact_id=source['record']['id'], anchor_sha256=source['record']['sha256'],
                palette=measure_palette(source['path']), observed=None, note='Measured palette only; material observation not available')


def ensure(project_id, project, style_reference_ids, priority=0):
    """Automation gate: ('none'|'ready'|'pending', profile). Never waits on a failed analysis."""
    if mode(project) == 'image': return 'none', None
    source = anchor(project_id, project, style_reference_ids)
    if not source: return 'none', None
    found = find(project_id, source['record']['sha256'])
    if found: return 'ready', found
    from engines.style_profile import POLICY_VERSION
    own = [j for j in jobs.listing() if j['payload'].get('kind') == 'style_profile' and j['payload'].get('anchor_sha256') == source['record']['sha256']
           and j['payload'].get('project_id') == project_id and j['payload'].get('policy_version') == POLICY_VERSION]
    if any(j['status'] not in jobs.TERMINAL for j in own): return 'pending', None
    if own: return 'ready', measured_only(source)  # analysis ended without a profile; continue on the measured palette
    jobs.enqueue(dict(kind='style_profile', project_id=project_id, artifact_id=source['record']['id'], anchor_sha256=source['record']['sha256'],
                      policy_version=POLICY_VERSION, use_gpu=False, timeout_seconds=900, priority=priority))
    return 'pending', None


def concept_style(project_id, project, style_reference_ids=()):
    """Style text and lock identity for a concept request, or None in image mode / without an anchor."""
    from engines.style_profile import style_text, fingerprint
    if mode(project) == 'image': return None
    source = anchor(project_id, project, style_reference_ids)
    if not source: return None
    profile = find(project_id, source['record']['sha256'])
    if not profile:
        ensure(project_id, project, style_reference_ids)  # paths that do not wait (manual/Expert) still queue the shared analysis
        profile = measured_only(source)
    stored = {k: v for k, v in profile.items() if k not in ('artifact_id', 'sha256')}
    return dict(text=style_text(profile), identity=dict(anchor_sha256=source['record']['sha256'], policy_version=profile['policy_version'],
                profile_sha256=fingerprint(stored), artifact_id=profile.get('artifact_id'), observed=bool(profile.get('observed'))))


def execute(job, folder):
    from engines.style_profile import measure_palette, observe, POLICY_VERSION
    p = job['payload']; record = store.get_artifact(p['artifact_id']); path = store.safe_path(record['relative_path'])
    if store.digest(path) != p['anchor_sha256'] or record['sha256'] != p['anchor_sha256']: raise ValueError('Style reference changed after admission')
    with (folder / 'worker.log').open('a', encoding='utf-8') as log:
        def progress(message): log.write('STAGE ' + message + '\n'); log.flush()
        profile = dict(policy_version=POLICY_VERSION, anchor_artifact_id=record['id'], anchor_sha256=record['sha256'], palette=measure_palette(path), observed=None)
        try: profile['observed'] = observe(path, progress)
        except (OSError, ValueError, TimeoutError) as exc: profile['note'] = 'Material observation unavailable: ' + str(exc)[:300]
    target = folder / 'style_profile.json'; part = folder / 'style_profile.json.part'
    part.write_text(json.dumps(profile, indent=2), encoding='utf-8'); part.replace(target)
    store.add_artifact(target, 'style_profile', 'Style profile (materials, colours, rendering; no shape)', dict(project_id=p['project_id'], job_id=job['id'],
        anchor_artifact_id=record['id'], anchor_sha256=record['sha256'], policy_version=POLICY_VERSION, artistic_approval=False))
    jobs.transition(job['id'], 'GENERATED'); jobs.transition(job['id'], 'VALIDATING'); jobs.transition(job['id'], 'REVIEW_REQUIRED')


from fastapi import APIRouter
router = APIRouter(prefix='/api')


@router.get('/projects/{project_id}/style-profile')
def read(project_id: str):
    """Read-only view for Settings; reading never queues an analysis."""
    from .studio import project as load
    from engines.style_profile import POLICY_VERSION, style_text
    value = load(project_id); source = anchor(project_id, value)
    if not source: return dict(mode=mode(value), status='no_anchor')
    found = find(project_id, source['record']['sha256'])
    pending = any(j['payload'].get('kind') == 'style_profile' and j['payload'].get('anchor_sha256') == source['record']['sha256'] and j['payload'].get('policy_version') == POLICY_VERSION
                  and j['status'] not in jobs.TERMINAL for j in jobs.listing())
    profile = found or measured_only(source)
    observed = (profile.get('observed') or {}).get('observation')
    return dict(mode=mode(value), anchor_artifact_id=source['record']['id'], status='ready' if found and observed else 'analyzing' if pending else 'measured_only',
                text=style_text(profile), palette=profile['palette']['entries'], materials=(observed or {}).get('materials', []),
                rendering=(observed or {}).get('rendering_style'), stylization=(observed or {}).get('stylization'))


def terrain_colours(project_id, project, style_reference_ids=()):
    """Provisional world colours from the project palette: a green for grass, a warm earth tone for roads (else defaults)."""
    import colorsys
    if mode(project) == 'image' and not style_reference_ids: return {}
    source = anchor(project_id, project, style_reference_ids)
    if not source: return {}
    entries = (find(project_id, source['record']['sha256']) or measured_only(source))['palette']['entries']
    def hls(entry): return colorsys.rgb_to_hls(*(int(entry['hex'][i:i + 2], 16) / 255 for i in (1, 3, 5)))
    greens = [e for e in entries if 70 <= hls(e)[0] * 360 < 170 and hls(e)[2] > 0.15]
    earth = [e for e in entries if 15 <= hls(e)[0] * 360 < 60 and 0.25 <= hls(e)[1] <= 0.65]
    result = {}
    if greens: result['grass_color'] = max(greens, key=lambda e: e['share'])['hex']
    if earth: result['road_color'] = max(earth, key=lambda e: e['share'])['hex']
    return result


def accent_colour(project_id, project, minimum_saturation=0.35):
    """A genuinely saturated palette colour (e.g. cyan mana) for effect accents; muted palettes get none."""
    import colorsys
    if mode(project) == 'image': return None
    source = anchor(project_id, project)
    if not source: return None
    entries = (find(project_id, source['record']['sha256']) or measured_only(source))['palette']['entries']
    def saturation(entry): return colorsys.rgb_to_hls(*(int(entry['hex'][i:i + 2], 16) / 255 for i in (1, 3, 5)))[2]
    vivid = [e for e in entries if e['share'] >= 0.02 and saturation(e) >= minimum_saturation]
    return max(vivid, key=saturation)['hex'] if vivid else None
