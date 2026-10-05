let csrfToken = '';
export function setCsrfToken(value: string) { csrfToken = value; }
export class ApiError extends Error { constructor(message: string, public status: number) {super(message);} }
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isForm = init.body instanceof FormData;
  if (init.body && !isForm) headers.set('Content-Type','application/json');
  if (init.method && !['GET','HEAD'].includes(init.method)) headers.set('X-CSRF-Token',csrfToken);
  const response = await fetch(`/api${path}`, {...init,headers,credentials:'same-origin',cache:'no-store'});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((x: {loc?:string[];msg:string}) => `${x.loc?.slice(1).join('.')}: ${x.msg}`).join(' · ') : `请求失败 (${response.status})`;
    throw new ApiError(message,response.status);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export const post = <T>(path:string,body:unknown) => api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const patch = <T>(path:string,body:unknown) => api<T>(path,{method:'PATCH',body:JSON.stringify(body)});
