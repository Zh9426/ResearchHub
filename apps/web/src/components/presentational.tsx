import type {ReactNode} from 'react';
import {zh} from '../lib/zh';
export const human=zh;
export const date=(value:unknown)=>value?new Date(String(value)).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
export function Status({value}:{value:unknown}) {const status=String(value??'unknown');return <span className={`status status-${status}`}>{human(status)}</span>;}
export function Empty({children='暂无记录。创建第一条科研记录以开始。'}:{children?:ReactNode}) {return <div className="empty">{children}</div>;}
export function Feedback({loading,error}:{loading?:boolean;error?:string}) {return loading?<p className="empty" role="status">正在加载科研工作区…</p>:error?<p className="error" role="alert">{error}</p>:null;}
export function Panel({title,action,children,className=''}:{title:string;action?:ReactNode;children:ReactNode;className?:string}) {return <section className={`panel ${className}`}><header className="panel-heading"><h2>{title}</h2>{action}</header>{children}</section>;}
