'use client';
import {useState} from 'react';
import Link from 'next/link';
import type {ProjectContext,RunContext} from '../../../../packages/shared/types';
import {useData} from '@/lib/use-data';
import {compareContexts,type ComparisonRow} from '@/lib/compare';
import {Panel,Status,Feedback,Empty} from './ui';
function ComparisonTable({rows}:{rows:ComparisonRow[]}){return !rows.length?<Empty>两条 Run 均未填写此类数据。</Empty>:<div className="table-scroll"><table><thead><tr><th>Name</th><th>Run A</th><th>Run B</th><th>Difference</th></tr></thead><tbody>{rows.map(row=><tr className={row.different?'different':''} key={row.name}><th>{row.name}</th><td className="mono">{row.left}</td><td className="mono">{row.right}</td><td>{row.different?'changed':'same'}</td></tr>)}</tbody></table></div>}
export function Compare({context}:{context:ProjectContext}){
 const [a,setA]=useState(context.runs[0]?.id??''),[b,setB]=useState(context.runs[1]?.id??'');
 const left=useData<RunContext>(a?`/runs/${a}/context`:null),right=useData<RunContext>(b?`/runs/${b}/context`:null);
 const diff=left.data&&right.data?compareContexts(left.data,right.data):null;
 return <><Panel title="Compare Runs"><div className="comparison-selector">{([{name:'Run A',value:a,update:setA},{name:'Run B',value:b,update:setB}]).map(x=><label className="field" key={x.name}><span>{x.name}</span><select value={x.value} onChange={e=>x.update(e.target.value)}><option value="">选择 Run</option>{context.runs.map(row=><option key={row.id} value={row.id}>{String(row.title)}</option>)}</select></label>)}</div>{a===b&&a&&<p className="boundary">请选择两个不同的 Research Run。</p>}</Panel><Feedback loading={left.loading||right.loading} error={left.error||right.error}/>{diff&&left.data&&right.data&&<><Panel title="Status / Conclusions"><div className="comparison-heads">{[left.data,right.data].map((x,i)=><div key={i}><h3><Link href={`/runs/${x.run.id}`}>{String(x.run.title)}</Link></h3><Status value={x.run.status}/><p>Scientific outcome: <Status value={x.run.scientific_outcome}/></p><p><strong>Human Conclusion</strong><br/>{String(x.run.human_conclusion||'unknown')}</p><p><strong>Artifacts summary</strong><br/>{x.artifacts.length} files · {x.artifacts.map(f=>String(f.filename)).join(', ')||'none'}</p></div>)}</div></Panel><Panel title="Parameter Differences"><ComparisonTable rows={diff.parameters}/></Panel><Panel title="Metric Differences"><ComparisonTable rows={diff.metrics}/></Panel></>}</>;
}
