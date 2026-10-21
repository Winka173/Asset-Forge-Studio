import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', workers: 1, use: { baseURL: 'http://127.0.0.1:8765', channel: 'chrome', headless: true, viewport: {width: 1600, height: 1100} }, reporter: 'list' });
