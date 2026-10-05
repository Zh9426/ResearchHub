export type Json = null | boolean | number | string | Json[] | {[key:string]:Json};
export type RecordData = {id:string;project_id?:string;title?:string;name?:string;status?:string;created_at?:string;updated_at?:string;[key:string]:unknown};
export interface Project extends RecordData {name:string;description:string;module_id:string;current_stage:string|null;is_demo?:boolean;}
export interface Schema {id:string;name:string;value_type:string;unit:string;description?:string;}
export interface Stage {id:string;name:string;description:string;}
export interface GateDefinition extends Stage {stage_id:string;criteria:RecordData[];}
export interface ModuleManifest {id:string;name:string;version:string;description:string;run_types:(string|{id:string;name:string})[];parameter_schemas:Schema[];metric_schemas:Schema[];research_stages:Stage[];stage_gates:GateDefinition[];artifact_categories:string[];navigation:(string|{id:string;label?:string;name?:string})[];custom_views:(string|{id:string;label?:string;name?:string;description?:string})[];dashboard_widgets:unknown[];}
export interface ProjectContext {project:Project;module:ModuleManifest;runs:RecordData[];tasks:RecordData[];milestones:RecordData[];questions:RecordData[];hypotheses:RecordData[];evidence:RecordData[];claims:RecordData[];sources:RecordData[];notes:RecordData[];decisions:RecordData[];risks:RecordData[];artifacts:RecordData[];gates:RecordData[];activity:RecordData[];}
export interface RunContext {run:RecordData;parameters:RecordData[];metrics:RecordData[];artifacts:RecordData[];evidence:RecordData[];parent:RecordData|null;children:RecordData[];changes_from_parent:unknown;}
export interface AuthResponse {user:{id:string;email:string;display_name:string};csrf_token:string;}
