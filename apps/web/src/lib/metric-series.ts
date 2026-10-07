import type {RecordData} from '../../../../packages/shared/types';
export function metricSeries(rows:RecordData[]){
 const groups=new Map<string,{unit:string|null;points:{id:string;x:number;y:number;title:string}[]}>();
 for(const row of rows){const unit=row.unit==null?null:String(row.unit),key=JSON.stringify(unit),time=Date.parse(String(row.created_at));if(typeof row.value!=='number'||!Number.isFinite(row.value)||!Number.isFinite(time))continue;const group=groups.get(key)??{unit,points:[]};group.points.push({id:row.id,x:time,y:row.value,title:String((row.run as RecordData|undefined)?.title??row.name)});groups.set(key,group);}
 return [...groups.values()].map(group=>({...group,points:group.points.sort((a,b)=>a.x-b.x)}));
}
