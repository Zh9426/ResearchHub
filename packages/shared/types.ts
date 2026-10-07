export type Json = null | boolean | number | string | Json[] | {[key:string]:Json};
export type RecordData = {id:string;project_id?:string;title?:string;name?:string;status?:string;created_at?:string;updated_at?:string;[key:string]:unknown};
export interface Project extends RecordData {name:string;description:string;module_id:string;current_stage:string|null;is_demo?:boolean;}
export interface Schema {id:string;name:string;value_type:string;unit:string;description?:string;required?:boolean;optional?:boolean;default?:Json;display_group?:string;order?:number;help_text?:string;visibility?:'basic'|'advanced';capability?:string|null;optimization_direction?:'maximize'|'minimize'|'target_range'|'informational';target_range?:number[];}
export interface RunFormGroup {id:string;name:string;fields:string[];visibility?:'basic'|'advanced';}
export interface RunForm {run_type:string;capability?:string|null;groups:RunFormGroup[];}
export interface Capability {id:string;name:string;description:string;}
export interface Stage {id:string;name:string;description:string;}
export interface GateDefinition extends Stage {stage_id:string;criteria:RecordData[];}
export interface ViewDefinition {id:string;name?:string;label?:string;description?:string;run_types?:string[];metric_ids?:string[];artifact_categories?:string[];evidence_filters?:{status?:string[];type?:string[]};layout_type?:'research'|'runs'|'metrics'|'evidence'|'artifacts'|'lineage'|'hardware'|'lab';}
export interface WidgetDefinition extends ViewDefinition {kind:string;}
export interface ModuleManifest {id:string;name:string;version:string;description:string;run_types:(string|{id:string;name:string;capability?:string|null})[];parameter_schemas:Schema[];metric_schemas:Schema[];context_fields?:Schema[];run_forms?:RunForm[];default_capabilities?:string[];research_stages:Stage[];stage_gates:GateDefinition[];artifact_categories:string[];navigation:(string|{id:string;label?:string;name?:string})[];custom_views:(string|ViewDefinition)[];dashboard_widgets:(string|WidgetDefinition)[];}
export interface ProjectContext {project:Project;module:ModuleManifest;runs:RecordData[];tasks:RecordData[];milestones:RecordData[];questions:RecordData[];hypotheses:RecordData[];evidence:RecordData[];claims:RecordData[];sources:RecordData[];notes:RecordData[];decisions:RecordData[];risks:RecordData[];artifacts:RecordData[];gates:RecordData[];activity:RecordData[];tags?:RecordData[];}
export interface RunContext {run:RecordData;parameters:RecordData[];metrics:RecordData[];artifacts:RecordData[];evidence:RecordData[];parent:RecordData|null;children:RecordData[];changes_from_parent:unknown;referenced_artifacts?:RecordData[];worksheet_parameters?:RecordData[];worksheet_metrics?:RecordData[];worksheet_parameters_incomplete?:boolean;worksheet_metrics_incomplete?:boolean;parameters_total?:number;metrics_total?:number;parameter_diff_incomplete?:boolean;}
export interface AuthResponse {user:{id:string;email:string;display_name:string};csrf_token:string;}
export interface QueryPage<T> {items:T[];total:number;limit:number;offset:number;}
export interface ProjectSummary {project:Project;module:ModuleManifest;counts:Record<string,number>;highlighted_runs:RecordData[];recent_runs:RecordData[];current_tasks:RecordData[];evidence_summary:Record<string,number>;current_gates:RecordData[];current_risks:RecordData[];current_decisions:RecordData[];}
export interface DiffRow extends RecordData {name:string;change_type:string;fields:Record<string,{parent:unknown;current:unknown}>;parent_record:RecordData|null;current_record:RecordData|null;}
export interface LineagePage {nodes:RecordData[];total:number;limit:number;offset:number;truncated:boolean;}
export interface TraceResult {subject:RecordData;groups:Record<string,QueryPage<RecordData>>;}
