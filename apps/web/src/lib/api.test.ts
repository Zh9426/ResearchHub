import {describe,it,expect,vi,afterEach} from 'vitest';
import {api,setCsrfToken,ApiError} from './api';
afterEach(()=>vi.unstubAllGlobals());
describe('API client security',()=>{
  it('写请求发送 CSRF 且禁用数据缓存',async()=>{const mock=vi.fn().mockResolvedValue(new Response('{}',{status:200}));vi.stubGlobal('fetch',mock);setCsrfToken('test-token');await api('/notes/x',{method:'PATCH',body:'{}'});const init=mock.mock.calls[0][1];expect(init.headers.get('X-CSRF-Token')).toBe('test-token');expect(init.cache).toBe('no-store');expect(init.credentials).toBe('same-origin');});
  it('权限错误不会回落到 mock 数据',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Forbidden'}),{status:403})));await expect(api('/projects')).rejects.toBeInstanceOf(ApiError);});
});
