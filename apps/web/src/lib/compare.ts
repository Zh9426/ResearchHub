import type {RunContext,RecordData} from '../../../../packages/shared/types';
export interface ComparisonRow {name:string;left:string;right:string;different:boolean;}
const value=(x:RecordData|undefined)=>x?`${JSON.stringify(x.value)} ${x.unit??''}`.trim():'unknown';
export function compareRows(left:RecordData[],right:RecordData[]):ComparisonRow[]{const names=new Set([...left,...right].map(x=>String(x.name)));return [...names].map(name=>{const a=value(left.find(x=>x.name===name)),b=value(right.find(x=>x.name===name));return{name,left:a,right:b,different:a!==b};});}
export function compareParameterRows(left:RecordData[],right:RecordData[]):ComparisonRow[]{
 return compareRows(left,right).map(row=>{
  const render=(item:RecordData|undefined)=>item?`${value(item)} · ${String(item.source_kind??'unknown')} · ${item.is_confirmed?'confirmed':'unconfirmed'} · uncertainty ${String(item.uncertainty??'unknown')} · conditions ${String(item.valid_conditions??'unknown')} · source ${String(item.source_id??'unknown')} / ${String(item.source_location??'unknown')}`:'unknown';
  const a=render(left.find(x=>x.name===row.name)),b=render(right.find(x=>x.name===row.name));
  return {...row,left:a,right:b,different:a!==b};
 });
}
export function compareContexts(a:RunContext,b:RunContext){return{parameters:compareParameterRows(a.parameters,b.parameters),metrics:compareRows(a.metrics,b.metrics).map(row=>{const render=(items:RecordData[],text:string)=>`${text} · ${String(items.find(x=>x.name===row.name)?.status??'unknown')}`;const left=render(a.metrics,row.left),right=render(b.metrics,row.right);return {...row,left,right,different:left!==right};})};}
