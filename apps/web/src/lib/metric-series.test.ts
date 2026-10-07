import {describe,it,expect} from 'vitest';
import {metricSeries} from './metric-series';
describe('科研指标时间序列',()=>{
 it('空值和非数值不补零，未知单位与不同单位分组',()=>{const rows=[{id:'zero',value:0,unit:null,created_at:'2026-10-06T01:00:00Z'},{id:'known',value:2,unit:'Pa',created_at:'2026-10-06T02:00:00Z'},{id:'null',value:null,unit:'Pa',created_at:'2026-10-06T03:00:00Z'},{id:'string',value:'3',unit:'Pa',created_at:'2026-10-06T03:00:00Z'},{id:'bool',value:true,unit:'Pa',created_at:'2026-10-06T03:00:00Z'},{id:'bad',value:NaN,created_at:'invalid'}];const groups=metricSeries(rows);expect(groups).toHaveLength(2);expect(groups[0]).toMatchObject({unit:null,points:[{id:'zero',y:0}]});expect(groups[1]).toMatchObject({unit:'Pa',points:[{id:'known',y:2}]});});
 it('只根据实际保存时间排序，保留相同时间多个记录',()=>{const groups=metricSeries([{id:'later',value:3,unit:'',created_at:'2026-10-06T02:00:00Z'},{id:'early',value:2,unit:'',created_at:'2026-10-06T01:00:00Z'},{id:'same',value:4,unit:'',created_at:'2026-10-06T01:00:00Z'}]);expect(groups[0].points.map(p=>p.id)).toEqual(['early','same','later']);});
});
