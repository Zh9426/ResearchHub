'use client';
import Link from 'next/link';
import type {ProjectContext} from '../../../../packages/shared/types';
import {Panel,Status,Empty} from './ui';
import {RunList} from './run-list';
const areas:Record<string,{title:string;description:string;runTypes:string[]}>={
 probe_architecture:{title:'Probe Architecture',description:'记录探头架构候选、共同几何约束与方案否决。结构选择必须保留适用边界。',runTypes:['controlled_probe_comparison','prototype_validation']},
 acoustic_screening:{title:'Acoustic Screening',description:'数值可信度与声学筛选：固定评价 ROI、冻结参考、覆盖与目标外泄漏。声学代理量不替代实测材料响应。',runTypes:['numerical_validation','controlled_probe_comparison','robustness_test']},
 beam_steering:{title:'Beam Steering',description:'比较偏转条件、主瓣与外域峰值，保存控制条件和适用角度。',runTypes:['steering_test','robustness_test']},
 sequential_scanning:{title:'Sequential Scanning',description:'记录扫描路径、停留时间及冻结评价条件，区分扫描协议与单点声场结果。',runTypes:['scan_protocol_test']},
 imaging:{title:'Imaging',description:'记录成像 PSF、分辨率与声驱动条件；双功能探头需独立评估成像性能。',runTypes:['imaging_psf']},
 kwave_validation:{title:'k-Wave Validation',description:'保存 k-Wave 复核环境、网格与代码版本，关联数值限制和独立验证证据。',runTypes:['kwave_validation','numerical_validation']},
 electroacoustics:{title:'Electroacoustics',description:'电声驱动与原型测量；未知驱动参数保持 unknown，平方速度积分不等同真实电声功率。',runTypes:['prototype_validation','hydrophone_measurement']},
 hydrophone_measurement:{title:'Hydrophone Measurement',description:'保存水听器校准、测量条件、不确定度与声场原始数据。',runTypes:['hydrophone_measurement']},
 material_response:{title:'Material Response',description:'记录实测材料响应、阈值来源与重复性。未测得的阈值保持 null，不从声学覆盖直接推断固化覆盖。',runTypes:['material_response']},
 thermal_flow:{title:'Thermal / Flow',description:'记录温度、流动边界与实验条件，评估模型到物理环境的迁移。',runTypes:['thermal_flow_test']},
 dual_function_coexistence:{title:'Dual-function Coexistence',description:'成像与驱动共存，检查串扰、热影响及功能互相约束。',runTypes:['imaging_psf','prototype_validation','thermal_flow_test']},
 tank_validation:{title:'Tank Validation',description:'将原型与水槽声场测量关联，归档重新标定及独立复核证据。',runTypes:['prototype_validation','hydrophone_measurement']},
 phantom_ex_vivo:{title:'Phantom / Ex-vivo',description:'模型体或离体功能验证。保存封堵判据与证据边界，数值通过不能代替实验评审。',runTypes:['phantom_test']}
};
export function DomainView({id,context}:{id:string;context:ProjectContext}){
 const area=areas[id]??{title:id,description:context.module.description,runTypes:[id]};
 const runs=context.runs.filter(r=>area.runTypes.includes(String(r.run_type))),runIds=new Set(runs.map(r=>r.id));
 const evidence=context.evidence.filter(e=>runIds.has(String(e.linked_run_id))),artifacts=context.artifacts.filter(a=>runIds.has(String(a.run_id)));
 return <><Panel title={area.title}><p className="section-copy">{area.description}</p><p className="section-copy">Run Types: {area.runTypes.join(' · ')}</p><RunList rows={runs}/></Panel><div className="overview-grid"><Panel title="Related Evidence">{evidence.length?<div className="compact-list">{evidence.map(e=><Link key={e.id} href={`/projects/${context.project.id}/evidence`}><div><strong>{String(e.title)}</strong><small>{String(e.limitations||'适用边界尚未填写')}</small></div><Status value={e.status}/></Link>)}</div>:<Empty>尚无关联该研究区域 Run 的 Evidence。</Empty>}</Panel><Panel title="Related Artifacts">{artifacts.length?<div className="compact-list">{artifacts.map(a=><Link key={a.id} href={`/api/artifacts/${a.id}/download`}><strong>{String(a.filename)}</strong><span>{String(a.category)}</span></Link>)}</div>:<Empty>尚无关联 Artifact。</Empty>}</Panel></div><Panel title="Research Context / Gates"><div className="compact-list">{context.gates.filter(g=>g.stage_id===context.project.current_stage).map(g=><Link key={g.id} href={`/projects/${context.project.id}/workflow`}><div><strong>{String(g.gate_id)} · {String(g.name)}</strong><small>{String(g.blocking_reason||'没有记录 Blocking Reason')}</small></div><Status value={g.status}/></Link>)}</div><p className="section-copy"><Link href={`/projects/${context.project.id}/research`}>查看项目 Risk 与 Research Questions →</Link></p></Panel></>;
}
