// Shared navigation for the minimal Create flow and collapsed controls used by native verification scripts.
// Step 2 ("Describe") holds only the prompt and reference; name, counts and engine options live in the Advanced section of step 3.

export async function toGenerateStep(page) {
  const advanced = page.locator('.create-advanced');
  if (await advanced.count()) return;
  await page.getByRole('button', {name: 'Continue to generation'}).click();
  await advanced.waitFor({state: 'attached'});
}

export async function openAdvanced(page) {
  await toGenerateStep(page);
  await page.locator('.create-advanced').evaluate(element => { element.open = true; });
}

// Fills the optional asset name from either step, returning to the step the caller was on.
export async function fillAssetName(page, value) {
  const field = page.getByLabel('Asset name', {exact: true});
  if (await field.isVisible().catch(() => false)) { await field.fill(value); return; }
  const prompt = page.locator('.prompt-input');
  const onDescribe = await prompt.isVisible().catch(() => false);
  let placeholder = false;
  if (onDescribe && !(await prompt.inputValue()).trim()) { await prompt.fill('pending asset description'); placeholder = true; }
  await openAdvanced(page);
  await field.fill(value);
  if (onDescribe) {
    await page.getByRole('button', {name: 'Edit input', exact: true}).click();
    if (placeholder) await page.locator('.prompt-input').fill('');
  }
}

// Reads the draft name without changing steps (the field is only rendered on the Generate step).
export async function readAssetName(page) {
  const field = page.getByLabel('Asset name', {exact: true});
  if (await field.isVisible().catch(() => false)) return field.inputValue();
  return page.evaluate(() => {
    try {
      const project = localStorage.getItem('afs.project');
      const saved = JSON.parse(localStorage.getItem('afs.draft.' + project) || 'null');
      return saved?.draft?.name ?? '';
    } catch { return ''; }
  });
}

export async function openAssetActions(page) {
  const menu = page.locator('.production-inspector .action-menu');
  if (await menu.count()) await menu.first().evaluate(element => { element.open = true; });
}

export async function openGpuPopover(page) {
  if (await page.locator('.gpu-live-details').count()) return;
  await page.locator('.gpu-chip').click();
  await page.locator('.gpu-popover').waitFor();
}
