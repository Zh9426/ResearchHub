import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {previewBinding,jsonHash,type PublicProjectBinding} from '../src/sync/binding';
import {digest} from '../../../packages/sync-protocol/src/browser';
import {payloadFor} from '../src/sync/wire';

test('PC Domain字段长度按Unicode码点精确阻断且保留原操作',()=>{
 const snapshot=JSON.parse(readFileSync('../../packages/project-modules/generic/manifest.json','utf8'));
 const pid=crypto.randomUUID(),id=crypto.randomUUID();
 const project={id:pid,module_snapshot:snapshot} as any;
 const payload={kind:'Run',id,project_id:pid,title:'🧪'.repeat(200),local_format_version:1,local_edit_version:1,run_type:'simulation',objective:'',observation:'',status:'planned',scientific_outcome:'unknown',context_data:{},is_highlighted:true,highlight_type:'🧪'.repeat(100),highlight_note:'🧪'.repeat(10000)};
 const op={object_id:id,project_id:pid,object_type:'Run',operation_type:'create',payload} as any;
 expect(()=>payloadFor(op,project)).not.toThrow();
 for(const [field,max] of [['title',200],['highlight_type',100],['highlight_note',10000]] as const){const bad={...op,payload:{...payload,[field]:'🧪'.repeat(max+1)}};const before=JSON.stringify(bad);expect(()=>payloadFor(bad,project)).toThrow(`payload.${field}`);expect(JSON.stringify(bad)).toBe(before);}
 const note={...op,object_type:'Note',payload:{kind:'Note',id,project_id:pid,title:'🧪'.repeat(200),body:'  \n ',local_format_version:1,local_edit_version:1}};
 expect(()=>payloadFor(note,project)).not.toThrow();expect(()=>payloadFor({...note,payload:{...note.payload,title:'🧪'.repeat(201)}},project)).toThrow('payload.title');
});
test('绑定预览：实际内容digest、严格字段与未授权边界',async()=>{
 expect((await previewBinding({semantic_project_id:'same-name'})).state).toBe('BLOCKED');
 const snapshot=JSON.parse(readFileSync('../../packages/project-modules/generic/manifest.json','utf8'));
 const principal={device_id:crypto.randomUUID(),actor_id:crypto.randomUUID(),actor_type:'human',role:'writer'} as const;
 const b:PublicProjectBinding={binding_version:1,semantic_project_id:crypto.randomUUID(),opaque_project_id:crypto.randomUUID(),module_snapshot:snapshot,module_snapshot_hash:await digest(snapshot),local_module_hash:{algorithm:'sha256-json-stringify',value:await jsonHash(snapshot)},capabilities:{protocol_version:2,schema_version:2,object_types:['ResearchRun','Note']},principal,principal_map:[principal],trust:{membership_epoch:1,key_epoch:1,manifest_head:'1'.repeat(64),owner_root:'2'.repeat(64),recovery_root:'3'.repeat(64),manifest_chain:[{unverified:true}]}};
 expect((await previewBinding(b)).state).toBe('UNVERIFIED');expect((await previewBinding({...b,unknown:true})).reasons).toContain('binding.unknown: unknown field');expect((await previewBinding({...b,module_snapshot:{...snapshot,name:'tampered'}})).reasons).toContain('module_snapshot_hash: content mismatch');
 expect((await previewBinding({...b,principal_map:[]})).state).toBe('BLOCKED');expect((await previewBinding({...b,principal_map:[null]})).state).toBe('BLOCKED');
 for(const field of ['device_id','actor_id']){const nil={...principal,[field]:'00000000-0000-0000-0000-000000000000'};expect((await previewBinding({...b,principal:nil,principal_map:[nil]})).state).toBe('BLOCKED');}
 const project={id:crypto.randomUUID(),scope:'SYNTHETIC',module_snapshot:snapshot,module_hash:b.local_module_hash.value} as any;expect((await previewBinding(b,project)).reasons.join()).toContain('names never merge');
 const op={payload:{kind:'Note',id:crypto.randomUUID(),project_id:project.id,title:'中文',body:' \n🧪\t',local_format_version:1,local_edit_version:1}} as any;
 Object.assign(op,{object_id:op.payload.id,project_id:op.payload.project_id,object_type:op.payload.kind});
 expect(payloadFor(op,project)).toEqual({title:'中文',content:' \n🧪\t'});expect(()=>payloadFor({...op,payload:{...op.payload,secret_extra:'lost?'}},project)).toThrow('payload.secret_extra');
 for(const patch of [{object_id:crypto.randomUUID()},{project_id:crypto.randomUUID()},{object_type:'Run'}])expect(()=>payloadFor({...op,...patch},project)).toThrow('mismatch');
});

test('冻结模块语境规则：与Python workflow.validate_context一致拒绝额外字段/错run_type/缺必填',()=>{
 const module=(name:string)=>JSON.parse(readFileSync(`../../packages/project-modules/${name}/manifest.json`,'utf8'));
 const check=(snapshot:any,run_type:string,context_data:any,status='planned')=>{const id=crypto.randomUUID(),project_id=crypto.randomUUID();return payloadFor({object_id:id,project_id,object_type:'Run',operation_type:'create',payload:{kind:'Run',id,project_id,title:'SYNTHETIC',local_format_version:1,local_edit_version:1,run_type,objective:'',observation:'',status,scientific_outcome:'unknown',is_highlighted:false,highlight_type:'',highlight_note:'',context_data}} as any,{id:project_id,module_id:snapshot.id,module_snapshot:snapshot} as any);};
 const generic=module('generic'),hdsp=module('hdsp'),ice=module('ice-sonocuring');
 expect(()=>check(generic,'simulation',{context:'旧3A语境'})).toThrow('payload.context_data.context');
 expect(()=>check(ice,'numerical_validation',{experiment_conditions:'旧3A条件'})).toThrow('payload.context_data.experiment_conditions');
 expect(()=>check(ice,'numerical_validation',{unexpected_events:'快照有定义但此run_type不适用'})).toThrow('payload.context_data.unexpected_events');
 expect(()=>check(hdsp,'phase_plate_design',{repository:'不适用于制造记录'})).toThrow('payload.context_data.repository');
 expect(check(hdsp,'phase_retrieval',{repository:' 保留 🧪 ',config:'未知'}).context_data).toEqual({repository:' 保留 🧪 ',config:'未知'});
 // A frozen future/custom snapshot may mark a defined field required; enforce before conversion.
 const required=structuredClone(generic);required.context_fields.find((f:any)=>f.id==='repository').required=true;
 for(const status of ['running','completed'])expect(()=>check(required,'simulation',{},status)).toThrow('payload.context_data.repository');
 expect(()=>check(required,'simulation',{},'planned')).not.toThrow();
 expect(()=>check(generic,'simulation',{repository:'x'.repeat(65537)})).toThrow('payload.context_data');
});
