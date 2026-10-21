// Browser build uses same-origin API; future Tauri build sets one base URL.
// No filesystem, model, SQLite, or Blender implementation belongs in the frontend.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
export function apiFetch(path: string, init?: RequestInit) { return fetch(API_BASE + path, init); }
export function apiUrl(path: string): string;
export function apiUrl(path: undefined): undefined;
export function apiUrl(path: string | undefined): string | undefined;
export function apiUrl(path: string | undefined) { return path === undefined ? undefined : API_BASE + path; }
