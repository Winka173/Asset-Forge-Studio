// Browser debug uses same-origin API. Desktop receives ephemeral credentials
// through a scoped native command; no token is persisted in browser storage.
let API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
let API_TOKEN = '';
export function configureDesktopApi(base: string, token: string) {
  const url = new URL(base);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1') throw new Error('Desktop backend must be loopback-only');
  API_BASE = base.replace(/\/$/, ''); API_TOKEN = token;
}
export function redactApiSecrets(value: string) {return value.replace(/([?&]afs_token=)[^&\s"']+/gi, '$1[redacted]');}
export function apiFetch(path: string, init?: RequestInit) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Relative local API path required');
  const headers = new Headers(init?.headers); if (API_TOKEN) headers.set('X-AFS-Token', API_TOKEN);
  return fetch(API_BASE + path, {...init, headers, credentials: 'omit'});
}
export function apiUrl(path: string): string;
export function apiUrl(path: undefined): undefined;
export function apiUrl(path: string | undefined): string | undefined;
export function apiUrl(path: string | undefined) {
  if (path === undefined) return undefined;
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Relative local artifact path required');
  const url = API_BASE + path;
  return API_TOKEN ? url + (path.includes('?') ? '&' : '?') + 'afs_token=' + encodeURIComponent(API_TOKEN) : url;
}
