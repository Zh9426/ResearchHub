'use client';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import {Copy} from 'lucide-react';
import {post} from '@/lib/api';
import type {RecordData} from '../../../../packages/shared/types';
import {Editor} from './ui';
import {f} from '@/lib/fields';
export function CloneRun({run,artifacts}:{run:RecordData;artifacts:RecordData[]}) {
 const [show,setShow]=useState(false),router=useRouter();
 return <><button onClick={()=>setShow(true)}><Copy size={16} aria-hidden/>克隆</button>{show&&<Editor title="基于此记录开始新研究" fields={[
  f('title','新记录标题','text',{required:true,default:`${run.title} · 后续研究`}),f('objective','新研究目标','textarea',{default:run.objective}),
  ...[['inherit_parameters','继承参数（保持未确认）'],['inherit_protocol','继承方案'],['inherit_environment','继承环境'],['inherit_software','继承软件版本'],['inherit_code','继承代码版本']].map(([key,label])=>f(key,label,'boolean',{default:true})),
  f('artifact_ids','引用已有文件（不复制字节）','multi',{options:artifacts.map(x=>({value:x.id,label:String(x.filename??x.title??x.id)})),hint:'只保存引用；不继承科研结论、证据确认、星标和完成状态。'}),
 ]} onClose={()=>setShow(false)} onSave={async body=>{const created=await post<RecordData>(`/runs/${run.id}/clone`,body);router.push(`/runs/${created.id}`);}}/>}</>;
}
