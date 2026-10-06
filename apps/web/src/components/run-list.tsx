'use client';
import Link from 'next/link';
import {Star} from 'lucide-react';
import type {RecordData} from '../../../../packages/shared/types';
import {date,Empty,human,Status} from './ui';
import {RunHighlight} from './run-highlight';
export function RunList({rows,onChange}:{rows:RecordData[];onChange?:()=>void}){
 const mark=(row:RecordData)=>onChange?<RunHighlight compact run={row} onChange={onChange}/>:row.is_highlighted?<Star size={16} fill="currentColor" aria-label="星标"/>:null;
 return !rows.length?<Empty>此范围暂无研究记录。可以新建记录或调整筛选。</Empty>:<>
  <div className="table-scroll desktop-run-table"><table><thead><tr><th>星标</th><th>研究记录 ID</th><th>标题</th><th>类型</th><th>运行状态</th><th>科研结果</th><th>更新时间</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{mark(row)}</td><td><Link className="mono" href={`/runs/${row.id}`}>#{row.id.slice(0,6)}</Link></td><td><Link href={`/runs/${row.id}`}>{String(row.title)}</Link></td><td>{human(row.run_type)}</td><td><Status value={row.status}/></td><td><Status value={row.scientific_outcome}/></td><td>{date(row.updated_at)}</td></tr>)}</tbody></table></div>
  <div className="mobile-run-list">{rows.map(row=><div key={row.id} className="mobile-run-row">{mark(row)}<Link href={`/runs/${row.id}`}><strong>{String(row.title)}</strong><p>{human(row.run_type)} · <Status value={row.status}/> <Status value={row.scientific_outcome}/></p><code>#{row.id.slice(0,8)}</code></Link></div>)}</div>
 </>;
}
