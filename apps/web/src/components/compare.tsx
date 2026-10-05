'use client';
import {useState} from 'react';
import Link from 'next/link';
import type {ProjectContext,RunContext} from '../../../../packages/shared/types';
import {useData} from '@/lib/use-data';
import {compareContexts,type ComparisonRow} from '@/lib/compare';
import {Panel,Status,Feedback,Empty,human} from './ui';
function ComparisonTable({rows}:{rows:ComparisonRow[]}){return !rows.length?<Empty>两条研究记录均未填写此类数据。</Empty>:<div className="table-scroll"><table><thead><tr><th>名称</th><th>记录 A</th><th>记录 B</th><th>差异</th></tr></thead><tbody>{rows.map(row=><tr className={row.different?'different':''} key={row.name}><th>{human(row.name)}</th><td className="mono">{row.left}</td><td className="mono">{row.right}</td><td>{row.different?"有变化":"相同"}</td></tr>)}</tbody></table></div>}
export function Compare({context}:{context:ProjectContext}){
 const [a,setA]=useState(context.runs[0]?.id??''),[b,setB]=useState(context.runs[1]?.id??'');
 const left=useData<RunContext>(a?`/runs/${a}/context`:null),right=useData<RunContext>(b?`/runs/${b}/context`:null);
 const diff=left.data&&right.data?compareContexts(left.data,right.data):null;
 return <><Panel title="研究记录比较"><div className="comparison-selector">{([{name:"记录 A",value:a,update:setA},{name:"记录 B",value:b,update:setB}]).map(x=><label className="field" key={x.name}><span>{x.name}</span><select value={x.value} onChange={e=>x.update(e.target.value)}><option value="">选择研究记录</option>{context.runs.map(row=><option key={row.id} value={row.id}>{String(row.title)}</option>)}</select></label>)}</div>{a===b&&a&&<p className="boundary">请选择两个不同的研究记录。</p>}</Panel><Feedback loading={left.loading||right.loading} error={left.error||right.error}/>{diff&&left.data&&right.data&&<><Panel title="状态与结论"><div className="comparison-heads">{[left.data,right.data].map((x,i)=><div key={i}><h3><Link href={`/runs/${x.run.id}`}>{String(x.run.title)}</Link></h3><Status value={x.run.status}/><p>科研结果: <Status value={x.run.scientific_outcome}/></p><p><strong>人工结论</strong><br/>{String(x.run.human_conclusion||'未知')}</p><p><strong>文件概况</strong><br/>{x.artifacts.length} 个文件 · {x.artifacts.map(f=>String(f.filename)).join(', ')||"无"}</p></div>)}</div></Panel><Panel title="参数差异"><ComparisonTable rows={diff.parameters}/></Panel><Panel title="指标差异"><ComparisonTable rows={diff.metrics}/></Panel></>}</>;
}
