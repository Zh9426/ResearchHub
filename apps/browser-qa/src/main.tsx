import {createRoot} from 'react-dom/client';
import {QaShell,QA_ORIGIN} from './QaShell';
import {Workbench} from './Workbench';
import {Diagnostics} from './Diagnostics';
if(location.origin!==QA_ORIGIN){document.body.textContent='拒绝启动：请使用固定隔离地址 '+QA_ORIGIN;}else{createRoot(document.getElementById('root')!).render(<QaShell><Workbench extension={context=><Diagnostics {...context}/>}/></QaShell>);}
