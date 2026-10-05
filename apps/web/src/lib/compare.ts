import type {RunContext,RecordData} from '../../../../packages/shared/types';
import {zh} from './zh';
export interface ComparisonRow {name:string;left:string;right:string;different:boolean;}
const value=(x:RecordData|undefined)=>x?`${JSON.stringify(x.value)} ${x.unit??''}`.trim():'未知';
export function compareRows(left:RecordData[],right:RecordData[]):ComparisonRow[]{const names=new Set([...left,...right].map(x=>String(x.name)));return [...names].map(name=>{const a=value(left.find(x=>x.name===name)),b=value(right.find(x=>x.name===name));return{name,left:a,right:b,different:a!==b};});}
export function compareParameterRows(left:RecordData[],right:RecordData[]):ComparisonRow[]{
 return compareRows(left,right).map(row=>{
  const render=(item:RecordData|undefined)=>item?`${value(item)} · ${zh(item.source_kind)} · ${item.is_confirmed?'已确认':'未确认'} · 不确定度 ${String(item.uncertainty??'未知')} · 适用条件 ${String(item.valid_conditions??'未知')} · 来源 ${String(item.source_id??'未知')} / ${String(item.source_location??'未知')}`:'未知';
  const a=render(left.find(x=>x.name===row.name)),b=render(right.find(x=>x.name===row.name));
  return {...row,left:a,right:b,different:a!==b};
 });
}
export function compareContexts(a:RunContext,b:RunContext){return{parameters:compareParameterRows(a.parameters,b.parameters),metrics:compareRows(a.metrics,b.metrics).map(row=>{const render=(items:RecordData[],text:string)=>`${text} · ${zh(items.find(x=>x.name===row.name)?.status)}`;const left=render(a.metrics,row.left),right=render(b.metrics,row.right);return {...row,left,right,different:left!==right};})};}
