import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
export const root=fileURLToPath(new URL('../../../',import.meta.url));
export const runtime=resolve(root,'storage/runtime/browser-local-qa');
export const dist=resolve(runtime,'dist');
export const origin='http://127.0.0.1:3313';
export const route=p=>p==='/'||p==='/diagnostics'||/^\/projects\/(generic|hdsp|ice)(\/(runs|notes)\/[a-zA-Z0-9-]+)?$/.test(p);
process.env.PLAYWRIGHT_BROWSERS_PATH=resolve(runtime,'browsers');
