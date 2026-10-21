// Explicit real inference verification against the user's production dataset.
// Not part of ordinary fixture QA. Uses the installed model, real concept/mask and GPU.
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const browser = await chromium.launch({channel: 'chrome', headless: true});
const page = await browser.newPage({viewport: {width: 1600, height: 1100}});
const errors = []; page.on('pageerror', e => errors.push(e.message));
const base = 'http://127.0.0.1:8765';
const evidence = {started_at: new Date().toISOString(), purpose: 'real production concept / actual GPU inference, not fixture', checks: {}};
const outfile = path.resolve('../../docs/evidence/web_real_flow.json');
async function state() { return (await (await page.request.get(base + '/api/status')).json()); }
async function job(id) { return (await (await page.request.get(base + '/api/jobs')).json()).find(j => j.id === id); }
async function until(fn, timeout = 300000) { const start = Date.now(); while (Date.now() - start < timeout) { const r = await fn(); if (r) return r; await new Promise(r => setTimeout(r, 500)); } throw Error('Real flow timed out'); }
try {
  await page.goto(base); await page.getByRole('heading', {name: /Archer Tower/}).waitFor();
  const source = (await state()).artifacts.find(a => a.role === 'reference' && a.metadata.has_transparency);
  if (!source) throw Error('No real alpha reference artifact');
  await page.getByRole('combobox', {name: 'Engine local'}).selectOption('triposg');
  await page.getByRole('combobox', {name: 'Ảnh đầu vào AI'}).selectOption(source.id);
  await page.getByRole('textbox', {name: 'Seeds', exact: true}).fill('44');
  const response = page.waitForResponse(r => r.url().endsWith('/api/jobs/tournament') && r.request().method() === 'POST');
  await page.getByRole('button', {name: 'Generate local'}).click();
  const res = await response; if (res.status() !== 201) throw Error(await res.text());
  const queued = await res.json(), initial = queued.jobs[0]; evidence.initial_job = initial.id;
  await until(async () => (await job(initial.id)).status === 'RUNNING');
  await until(async () => (await page.request.get(`${base}/api/jobs/${initial.id}/files`)).json().then(files => files.some(f => f.name === 'process.json')));
  const processInfo = await (await page.request.get(`${base}/api/jobs/${initial.id}/files/process.json`)).json();
  evidence.cancelled_pid = processInfo.pid;
  const row = page.locator('.job-row').filter({hasText: initial.id.slice(0,10)});
  await row.getByRole('button', {name: 'Dừng'}).click();
  await until(async () => (await job(initial.id)).status === 'CANCELLED');
  evidence.checks.cancel_running_job = 'PASS';
  const retriedResponse = page.waitForResponse(r => r.url().endsWith(`/api/jobs/${initial.id}/retry`));
  await row.getByRole('button', {name: 'Retry attempt mới'}).click();
  const retry = await (await retriedResponse).json(); evidence.retry_job = retry.id;
  const done = await until(async () => { const j = await job(retry.id); if (['FAILED','BLOCKED'].includes(j.status)) throw Error(JSON.stringify(j)); return j.status === 'REVIEW_REQUIRED' ? j : null; });
  evidence.checks.real_inference = done.status;
  const all = await (await page.request.get(base + '/api/jobs')).json();
  const post = await until(async () => (await (await page.request.get(base + '/api/jobs')).json()).find(j => j.payload.parent_job === retry.id));
  evidence.blender_job = post.id;
  const processed = await until(async () => { const j = await job(post.id); if (['FAILED','BLOCKED'].includes(j.status)) throw Error(JSON.stringify(j)); return j.status === 'REVIEW_REQUIRED' ? j : null; }, 600000);
  evidence.checks.blender_postprocess = processed.status;
  const files = await (await page.request.get(`${base}/api/jobs/${post.id}/files`)).json();
  const manifest = await (await page.request.get(`${base}/api/jobs/${post.id}/files/output/report.json`)).json();
  evidence.checks.glb_reopen = manifest.checks.export_reopen;
  evidence.checks.fbx_reopen = manifest.checks.fbx_reopen;
  evidence.output_file_count = files.length;
  evidence.framing = manifest.framing;
  if (manifest.checks.export_reopen !== 'PASS' || manifest.checks.fbx_reopen !== 'PASS') throw Error('Export reopen failed');
  // Show the textured TRELLIS result, not an untextured shape as an apparent PBR result.
  const s = await state();
  const parent = s.artifacts.find(a => a.metadata.engine === 'trellis2_community' && a.metadata.seed === 43 && a.metadata.generation);
  const final = s.artifacts.find(a => a.metadata.parent_id === parent?.id && a.metadata.stage === 'blender_processed');
  await page.reload();
  await page.getByRole('combobox', {name: 'candidate', exact: true}).selectOption(final.id);
  await until(async () => (await page.locator('.viewer').getAttribute('data-loaded')) === '1');
  await page.getByRole('combobox', {name: 'Góc camera'}).selectOption('three_quarter');
  await page.locator('.viewer canvas').screenshot({path: '../../docs/evidence/real_webgl_canvas.png'});
  await page.screenshot({path: '../../docs/evidence/real_workbench.png'});
  evidence.checks.real_webgl_viewer = 'PASS'; evidence.checks.meshy_3d_comparison = 'BLOCKED_NO_GOLDEN_GLB';
  evidence.browser_errors = errors;
  if (errors.length) throw Error(errors.join('\n'));
  evidence.result = 'PASS';
} catch(e) { evidence.result = 'FAIL'; evidence.error = String(e); throw e; }
finally { evidence.finished_at = new Date().toISOString(); fs.writeFileSync(outfile, JSON.stringify(evidence,null,2)); await browser.close(); console.log(JSON.stringify(evidence)); }
