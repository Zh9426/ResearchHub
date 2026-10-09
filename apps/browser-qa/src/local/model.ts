// Browser QA working format. This is NOT SyncTransaction / frozen wire v1.
export const LOCAL_FORMAT_VERSION = 1 as const;
export type Identity = {id:'identity';workspace_id:string;device_id:string;scope:'SYNTHETIC_QA';authorization:'none'};
export type ModuleSnapshot = {id:string;version:string;name:string;run_types:{id:string;name:string}[];[key:string]:unknown};
export type Project = {id:string;route_alias:string;title:string;scope:'SYNTHETIC';module_id:string;module_version:string;module_snapshot:ModuleSnapshot;module_hash:string;local_format_version:1};
export const RUN_STATUSES=['planned','running','completed','failed','cancelled','blocked'] as const;
export const OUTCOMES=['unknown','positive_result','negative_result','inconclusive','candidate_rejected'] as const;
type Common = {id:string;project_id:string;title:string;local_format_version:1;local_edit_version:number};
export type Run = Common & {kind:'Run';run_type:string;objective:string;observation:string;status:typeof RUN_STATUSES[number];scientific_outcome:typeof OUTCOMES[number];is_highlighted:boolean;highlight_type:string;highlight_note:string;context_data:Record<string,string>};
export type Note = Common & {kind:'Note';body:string};
export type LocalObject=Run|Note;
export type LocalOperation={id:string;project_id:string;object_id:string;object_type:LocalObject['kind'];operation_type:'create'|'update'|'highlight';payload:LocalObject;known_base_revision:null;local_format_version:1;source:{workspace_id:string;device_id:string};state:'pending';wire_adapter:'NEEDS_WIRE_ADAPTER';created_at:string};
export type LocalAudit={id:string;operation_id:string;object_id:string;project_id:string;event:LocalOperation['operation_type'];local_edit_version:number;source:LocalOperation['source'];created_at:string;local_format_version:1};
export type LocalSnapshot={identity:Identity|null;projects:Project[];objects:LocalObject[];operations:LocalOperation[];audit:LocalAudit[]};
export function newDraft(project:Project,kind:LocalObject['kind']):LocalObject {
 const common={id:crypto.randomUUID(),project_id:project.id,title:'',local_format_version:LOCAL_FORMAT_VERSION,local_edit_version:0};
 return kind==='Note'?{...common,kind,body:''}:{...common,kind,run_type:project.module_snapshot.run_types[0].id,objective:'',observation:'',status:'planned',scientific_outcome:'unknown',is_highlighted:false,highlight_type:'',highlight_note:'',context_data:{}};
}
