import { canonicalBytes, validateDecimal, validateInteger } from './canonical-core.ts';

export interface ChangeSet extends Record<string, unknown> {
  change_id: string; audit_id: string; transaction_id: string; project_id: string;
  device_id: string; actor_id: string; actor_type: string; object_type: string;
  object_id: string; operation: string; parents: string[]; payload: Record<string, unknown>;
  schema_version: number; module_snapshot_hash: string; created_at: string;
}
export interface SyncTransaction extends Record<string, unknown> {
  transaction_id: string; idempotency_key: string; project_id: string; device_id: string;
  actor_id: string; actor_type: string; protocol_version: number; schema_version: number;
  created_at: string; ordered_change_ids: string[]; changes: ChangeSet[]; dependencies: string[];
}
export type ActorContext = Partial<Pick<SyncTransaction, 'project_id' | 'device_id' | 'actor_id' | 'actor_type'>>;
export class ProtocolError extends Error {
  code: string;
  constructor(code: string, message: string) { super(message); this.code = code; }
}
const changeFields = 'change_id audit_id transaction_id project_id device_id actor_id actor_type object_type object_id operation parents payload schema_version module_snapshot_hash created_at'.split(' ');
const transactionFields = 'transaction_id idempotency_key project_id device_id actor_id actor_type protocol_version schema_version created_at ordered_change_ids changes dependencies'.split(' ');
const payloadFields: Record<string, string[]> = Object.fromEntries(Object.entries({
  Project: 'name description module_id status current_stage current_objective enabled_capabilities repository module_version module_snapshot module_snapshot_hash',
  ResearchRun: 'title run_type parent_run_id objective hypothesis status scientific_outcome protocol observation ai_analysis human_conclusion next_step environment software_version code_revision repository branch commit_sha issue_url pull_request_url changes_from_parent started_at completed_at context_data artifact_ids tag_ids',
  Parameter: 'name value value_type unit source_kind source_id source_location uncertainty valid_conditions is_confirmed run_id status',
  Metric: 'name value value_type unit metric_schema_id status source_kind source_id source_location derivation uncertainty valid_conditions artifact_ids run_id is_confirmed',
  Artifact: 'run_id file_id filename mime_type category checksum sha256 size metadata sync_policy origin_device availability key_epoch blob_locator artifact_ids',
  Note: 'title content run_id tag_ids',
  Task: 'title description milestone_id status priority due_date tag_ids',
  Evidence: 'title description evidence_type status linked_run_id linked_artifact_id linked_source_id limitations tag_ids',
  Claim: 'title statement status limitations evidence_ids run_ids artifact_ids source_ids',
  Decision: 'title run_id context decision reason alternatives status evidence_ids tag_ids',
  Gate: 'gate_id stage_id name description status criteria evidence_ids blocking_reason',
  GateCriterion: 'id description provenance status evidence_ids gate_id',
  HumanConclusion: 'run_id content conclusion status evidence_ids',
  ModuleUpgrade: 'module_id from_version to_version module_version module_snapshot module_snapshot_hash expected_version expected_target_digest',
}).map(([key, value]) => [key, value.split(' ')]));
const evidenceStates = 'proposed unknown hypothesis assumed synthetic simulated measured calibrated validated reproduced rejected'.split(' ');
const enums: Record<string, string[]> = {
  source_kind: 'unknown synthetic assumed literature manufacturer measured calibrated derived'.split(' '),
  scientific_outcome: 'unknown positive_result negative_result inconclusive candidate_rejected'.split(' '),
  priority: ['low', 'medium', 'high', 'critical'], availability: ['pending', 'verified_reference', 'unavailable'],
  sync_policy: ['local_only', 'metadata_only', 'encrypted_sync', 'on_demand'],
  value_type: ['decimal', 'integer', 'number', 'string', 'boolean', 'object', 'array'],
};
const statuses: Record<string, string[]> = {
  Project: ['active', 'paused', 'completed', 'archived', 'blocked'],
  ResearchRun: ['planned', 'running', 'completed', 'failed', 'cancelled', 'blocked'],
  Parameter: evidenceStates, Metric: evidenceStates, Evidence: evidenceStates,
  Task: ['todo', 'doing', 'blocked', 'done'], Claim: ['draft', 'supported', 'rejected', 'inconclusive'],
  Decision: ['proposed', 'accepted', 'superseded', 'rejected'],
  Gate: ['not_started', 'in_progress', 'passed', 'failed', 'blocked'],
  GateCriterion: ['not_started', 'in_progress', 'passed', 'failed', 'blocked'],
  HumanConclusion: ['draft', 'proposed', 'final'],
};
const nullable = new Set('unit source_id source_location uncertainty valid_conditions repository current_stage parent_run_id branch commit_sha issue_url pull_request_url started_at completed_at milestone_id due_date run_id linked_run_id linked_artifact_id linked_source_id enabled_capabilities metric_schema_id derivation'.split(' '));
const objects = new Set(['metadata', 'context_data', 'module_snapshot']);
const arrays = new Set(['artifact_ids', 'tag_ids', 'evidence_ids', 'run_ids', 'source_ids', 'enabled_capabilities', 'criteria']);
function reject(message: string, code = 'INVALID_WIRE'): never { throw new ProtocolError(code, message); }
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function fields(value: unknown, expected: string[]): asserts value is Record<string, unknown> {
  if (!object(value) || Object.keys(value).length !== expected.length || expected.some(key => !Object.hasOwn(value, key))) reject('unknown or missing semantic fields');
}
function uuid(value: unknown): void {
  if (typeof value !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value) || value === '00000000-0000-0000-0000-000000000000') reject('invalid canonical UUID');
}
function hash(value: unknown): void { if (typeof value !== 'string' || !/^[0-9a-f]{64}$/.test(value)) reject('invalid digest'); }
function stamp(value: unknown): void {
  if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/.test(value) || value.startsWith('0000')) reject('invalid UTC millisecond datetime');
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) reject('invalid calendar datetime');
}
function version(value: unknown): void { if (value !== 1) reject('unsupported protocol/schema version', 'UPGRADE_REQUIRED'); }
function enumValue(value: unknown, allowed: string[]): void { if (typeof value !== 'string' || !allowed.includes(value)) reject('unknown enum value'); }
function setList(value: unknown, validate: (value: unknown) => void): asserts value is string[] {
  if (!Array.isArray(value)) reject('set must be an array');
  value.forEach(validate);
  if (value.some((entry, i) => i > 0 && value[i - 1] >= entry)) reject('set must be sorted and unique');
}
function payload(kind: string, value: unknown): void {
  if (!object(value) || Object.keys(value).some(key => !payloadFields[kind].includes(key))) reject('unknown business payload fields');
  for (const [key, item] of Object.entries(value)) {
    if (key === 'value' || (item === null && nullable.has(key))) continue;
    if (Object.hasOwn(enums, key)) enumValue(item, enums[key]);
    else if (key === 'status') enumValue(item, statuses[kind] ?? []);
    else if (objects.has(key)) { if (!object(item)) reject('payload object type mismatch'); }
    else if (arrays.has(key)) {
      if (!Array.isArray(item)) reject('payload array type mismatch');
      if (key.endsWith('_ids')) item.forEach(uuid);
      else if (key === 'enabled_capabilities' && item.some(v => typeof v !== 'string')) reject('capability must be string');
      else if (key === 'criteria') item.forEach(v => payload('GateCriterion', v));
    } else if (key === 'is_confirmed') { if (typeof item !== 'boolean') reject('confirmation must be boolean'); }
    else if (['size', 'key_epoch'].includes(key)) { if (typeof item !== 'number' || !Number.isSafeInteger(item) || item < 0) reject('count must be nonnegative integer'); }
    else if (['checksum', 'sha256', 'module_snapshot_hash', 'expected_target_digest'].includes(key)) hash(item);
    else if (['started_at', 'completed_at', 'due_date'].includes(key)) stamp(item);
    else if (key === 'origin_device' || (key.endsWith('_id') && !['module_id', 'metric_schema_id', 'gate_id', 'stage_id'].includes(key))) uuid(item);
    else if (typeof item !== 'string') reject('payload string type mismatch');
  }
  if (Object.hasOwn(value, 'value') && value.value !== null) {
    const type = value.value_type;
    try {
      if (type === 'decimal') validateDecimal(value.value);
      else if (type === 'integer') validateInteger(value.value);
      else if (type === 'number') reject('scientific number requires tagged decimal/integer');
      else if (['string', 'boolean', 'object', 'array'].includes(type as string)) {
        if ((type === 'string' && typeof value.value !== 'string') || (type === 'boolean' && typeof value.value !== 'boolean') || (type === 'object' && !object(value.value)) || (type === 'array' && !Array.isArray(value.value))) reject('value_type mismatch');
      } else if (!['string', 'boolean'].includes(typeof value.value)) reject('numeric values require explicit tagged value_type');
    } catch (error) { reject(String(error)); }
  }
  canonicalBytes(value);
}
export function validateChange(input: unknown): ChangeSet {
  fields(input, changeFields);
  for (const key of ['change_id', 'audit_id', 'transaction_id', 'project_id', 'device_id', 'actor_id', 'object_id']) uuid(input[key]);
  version(input.schema_version);
  enumValue(input.actor_type, ['human', 'codex', 'chatgpt', 'system']);
  enumValue(input.operation, ['create', 'update', 'archive', 'trash', 'restore', 'resolve']);
  enumValue(input.object_type, Object.keys(payloadFields));
  hash(input.module_snapshot_hash);
  stamp(input.created_at);
  setList(input.parents, hash);
  const count = input.parents.length;
  if ((input.operation === 'create' && count !== 0) || (input.operation === 'resolve' && count < 1) || (!['create','resolve'].includes(input.operation as string) && count !== 1)) reject('invalid parent count');
  payload(input.object_type as string, input.payload);
  return input as ChangeSet;
}

export function validateTransaction(input: unknown, context?: ActorContext): SyncTransaction {
  fields(input, transactionFields);
  for (const key of ['transaction_id', 'idempotency_key', 'project_id', 'device_id', 'actor_id']) uuid(input[key]);
  if (input.transaction_id !== input.idempotency_key) reject('idempotency key must equal transaction id');
  version(input.protocol_version); version(input.schema_version);
  enumValue(input.actor_type, ['human', 'codex', 'chatgpt', 'system']);
  stamp(input.created_at); setList(input.dependencies, uuid);
  if (input.dependencies.includes(input.transaction_id as string)) reject('self dependency');
  if (!Array.isArray(input.changes) || !input.changes.length || !Array.isArray(input.ordered_change_ids)) reject('transaction requires ordered nonempty changes');
  const objectIds = new Set<string>(), changeIds = new Set<string>(), audits = new Set<string>();
  const changes: ChangeSet[] = [];
  for (const member of input.changes) {
    const change = validateChange(member);
    for (const key of ['transaction_id', 'project_id', 'device_id', 'actor_id', 'actor_type', 'schema_version']) if (input[key] !== change[key]) reject('transaction member identity mismatch');
    const id = change.object_type + ':' + change.object_id;
    if (objectIds.has(id) || changeIds.has(change.change_id) || audits.has(change.audit_id)) reject('duplicate object/change/audit member');
    objectIds.add(id); changeIds.add(change.change_id); audits.add(change.audit_id); changes.push(change);
  }
  if (input.ordered_change_ids.length !== changes.length || input.ordered_change_ids.some((id, i) => id !== changes[i].change_id)) reject('ordered change ids mismatch');
  if (context) for (const key of ['project_id', 'device_id', 'actor_id', 'actor_type'] as const) if (Object.hasOwn(context, key) && input[key] !== context[key]) reject('wire identity differs from trusted context', 'ACTOR_CONTEXT_MISMATCH');
  canonicalBytes(input);
  return input as SyncTransaction;
}
