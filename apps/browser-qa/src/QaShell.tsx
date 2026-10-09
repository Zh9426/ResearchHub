import {useEffect,useState,type ReactNode} from 'react';
import {FlaskConical,FolderOpen} from 'lucide-react';
import {Panel,Empty} from '../../web/src/components/presentational';
import '../../web/src/app/globals.css';
import './qa.css';
import {initializeOfflineResources,verifyControlledShell} from './offline';

export const QA_ORIGIN='http://127.0.0.1:3313';
export function QaShell({children,sync=false,pc=false}:{children?:ReactNode;sync?:boolean;pc?:boolean}){
 const [ready,setReady]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{if(pc)return;let mounted=true;void verifyControlledShell().then(value=>{if(mounted)setReady(value);});return()=>{mounted=false;};},[]);
 async function initialize(){setBusy(true);setError('');try{await initializeOfflineResources();setReady(true);}catch(e){setReady(false);setError(`离线资源初始化失败：${String(e)}`);}finally{setBusy(false);}}
 return <div className="app-shell qa-shell"><a className="skip-link" href="#main">跳转到内容</a><aside className="sidebar"><a className="brand" href="/"><FlaskConical/><strong>Research Hub</strong></a><nav aria-label="合成项目">{['generic','hdsp','ice'].map(id=><a key={id} href={`/projects/${id}`}><FolderOpen/><span>{id.toUpperCase()} · SYNTHETIC</span></a>)}</nav><p className="sidebar-foot">浏览器本地 QA<br/>固定隔离工作区</p></aside><main id="main" className="main-shell"><div className="qa-banner" role="note">{pc?'PC 合成节点 · 受控同步实验版 · 仅合成数据':sync?'受控同步实验版 · 仅合成数据':'浏览器离线实验版 · 仅合成数据 · 未接入跨端同步'}</div><div className="workspace"><header className="page-heading"><div><h1>{/\/(runs|notes)\//.test(location.pathname)?'研究记录':'本地科研工作台'}</h1><p className="subtitle">合成工作区 · 本地记录与待处理状态</p></div></header>{!pc&&<div className={ready?"qa-offline-ready":""}><Panel title="离线启动"><div className="qa-content"><p data-testid="offline-status" role="status">{ready?'离线资源已就绪':'请先在线初始化离线资源'}</p><button className="primary" disabled={busy||ready} onClick={initialize}>{busy?'正在准备…':'初始化离线资源'}</button><p className="muted">{ready?'离线资源已缓存，可停止 QA 服务后查看和编辑本地记录。':'首次从未加载过应用时无法离线安装。请先准备离线资源。'}</p>{error&&<p role="alert" className="error">{error}</p>}</div></Panel></div>}{children??<Panel title="工作区"><Empty>请选择合成项目，开始本地记录。</Empty></Panel>}<p className="muted">传输：未配置 · 本轮尚未连接传输服务</p></div></main></div>;
}
