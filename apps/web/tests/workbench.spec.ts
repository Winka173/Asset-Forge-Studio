import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

test('real WebGL import, synchronized comparison and persisted human review', async ({page, request}) => {
  // Dedicated AFS_DATA=.local/browser-data. QA box is NOT an AI or Meshy result.
  const evidence = JSON.parse(fs.readFileSync(path.resolve('../../docs/evidence/blender_smoke.json'), 'utf8'));
  const file = path.join(evidence.run_path, 'output/LOD0.glb');
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading', {name: /Archer Tower/})).toBeVisible();
  await page.locator('label.upload').filter({hasText: 'Nhập golden GLB'}).locator('input').setInputFiles(file);
  await expect(page.locator('.model-cards article').first()).toContainText('LOD0.glb');
  await page.locator('label.upload').filter({hasText: 'Nhập local GLB'}).locator('input').setInputFiles(file);
  await expect(page.locator('.viewer')).toHaveAttribute('data-loaded', '2');
  await page.getByRole('combobox', {name: 'Góc camera'}).selectOption('back');
  await page.getByRole('checkbox', {name: 'Wireframe'}).check();
  await expect(page.getByRole('checkbox', {name: 'Wireframe'})).toBeChecked();
  await page.getByRole('checkbox', {name: 'Wireframe'}).uncheck();
  await page.getByRole('combobox', {name: 'Góc camera'}).selectOption('three_quarter');
  await page.getByPlaceholder('Tên người đánh giá').fill('QA fixture only');
  await page.getByPlaceholder(/Ví dụ/).fill('Real box smoke test, not an Archer Tower quality review.');
  await page.getByRole('button', {name: 'Lưu review'}).click();
  await expect(page.getByRole('status')).toContainText('Đã lưu đánh giá');
  const reviews = await (await request.get('/api/reviews')).json();
  expect(reviews.at(-1).payload.reviewer).toBe('QA fixture only');
  expect(reviews.at(-1).payload.decision).toBe('NEEDS_REVIEW');
  expect(errors).toEqual([]);
  await page.screenshot({path: '../../docs/evidence/workbench_qa_box.png', fullPage: true});
});
