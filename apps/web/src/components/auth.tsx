'use client';
import {useEffect,useState} from 'react';
import {Atom} from 'lucide-react';
import {api,post,setCsrfToken} from '@/lib/api';
import type {AuthResponse} from '../../../../packages/shared/types';
export function Auth({onLogin}:{onLogin:(auth:AuthResponse)=>void}) {
  const [setup,setSetup]=useState<boolean|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  useEffect(()=>{api<{setup_required:boolean}>('/auth/status').then(x=>setSetup(x.setup_required)).catch(e=>setError(e.message));},[]);
  return <main className="auth-page"><div className="auth-box"><div className="brand"><Atom aria-hidden/><strong>Research Hub</strong><small>v0.1</small></div><h1>{setup?'创建个人科研账号':'登录科研工作区'}</h1><p className="muted">项目、证据与实验记录保存在你独立运行的Research Hub。</p>{error&&<p className="error" role="alert">{error}</p>}{setup===null?<p role="status">正在连接 API…</p>:<form onSubmit={async event=>{event.preventDefault();setLoading(true);setError('');const form=new FormData(event.currentTarget);try{const auth=await post<AuthResponse>(setup?'/auth/setup':'/auth/login',{email:form.get('email'),password:form.get('password'),...(setup?{display_name:form.get('display_name')}: {})});setCsrfToken(auth.csrf_token);onLogin(auth);}catch(e){setError((e as Error).message);}finally{setLoading(false);}}}>{setup&&<label className="field"><span>显示名称</span><input name="display_name" required autoComplete="name"/></label>}<label className="field"><span>邮箱</span><input name="email" type="email" required autoComplete="username"/></label><label className="field"><span>密码{setup?'（至少 12 位）':''}</span><input name="password" type="password" required minLength={setup?12:undefined} autoComplete={setup?'new-password':'current-password'}/></label><button className="primary" disabled={loading}>{loading?'正在连接…':setup?'创建账号并进入':'登录'}</button></form>}</div></main>;
}
