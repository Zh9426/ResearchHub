import {describe,it,expect} from 'vitest';
import {compareRows,compareParameterRows} from './compare';
describe('Run comparison',()=>{it('缺失指标显示 unknown，零值不会丢失',()=>{expect(compareRows([{id:'a',name:'IoU',value:0}],[])).toEqual([{name:'IoU',left:'0',right:'unknown',different:true}]);});it('比较数值和单位而非创建日期',()=>{expect(compareRows([{id:'a',name:'frequency',value:4,unit:'MHz'}],[{id:'b',name:'frequency',value:4,unit:'MHz'}])[0].different).toBe(false);});});
it('同值 measured 与 assumed 参数仍然展示来源差异',()=>{const row=compareParameterRows([{id:'a',name:'frequency',value:4,source_kind:'assumed'}],[{id:'b',name:'frequency',value:4,source_kind:'measured'}])[0];expect(row.different).toBe(true);expect(row.left).toContain('assumed');expect(row.right).toContain('measured');});
