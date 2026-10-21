import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', workers: 1, timeout: 90000, use: { baseURL: process.env.AFS_TEST_URL || 'http://127.0.0.1:8767', channel: 'chrome', headless: true, viewport: {width: 1600, height: 1100} }, reporter: 'list' });
