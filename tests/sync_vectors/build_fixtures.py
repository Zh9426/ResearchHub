"""Fixture authoring utility: canonical anchors are handwritten, never encoder output."""
import copy
import hashlib
import json
from pathlib import Path

DEST = Path(__file__).resolve().parents[2] / "fixtures/sync/v1"
DEST.mkdir(parents=True, exist_ok=True)


def vector(name, value, canonical):
    data = canonical.encode("utf-8")
    return {"name": name, "input": value, "canonical": canonical, "hex": data.hex(), "sha256": hashlib.sha256(data).hexdigest()}


vectors = [
    vector("ascii", {"z":"text", "a":"quote\" slash\\ control\b\t\n\f\r\x00\x1f"}, '{"a":"quote\\\" slash\\\\ control\\b\\t\\n\\f\\r\\u0000\\u001f","z":"text"}'),
    vector("unicode_no_normalization", {"中文":"超声", "emoji":"😀", "combining":"e\u0301", "composed":"é"}, '{"combining":"é","composed":"é","emoji":"😀","中文":"超声"}'),
    vector("utf16_order", {"\ue000":"BMP", "😀":"astral"}, '{"😀":"astral","":"BMP"}'),
    vector("empty_null_booleans", {"null":None, "empty":"", "array":[], "object":{}, "bool":[True,False]}, '{"array":[],"bool":[true,false],"empty":"","null":null,"object":{}}'),
    vector("safe_integers", [0,-1,1,-9007199254740991,9007199254740991], '[0,-1,1,-9007199254740991,9007199254740991]'),
    vector("large_integer", {"value_type":"integer","value":"9000000000000000000"}, '{"value":"9000000000000000000","value_type":"integer"}'),
    vector("decimal_precision", [{"value_type":"decimal","value":"1.60","unit":"MPa"},{"value_type":"decimal","value":"1.600","unit":"MPa"},{"value_type":"decimal","value":"1e0","unit":None}], '[{"unit":"MPa","value":"1.60","value_type":"decimal"},{"unit":"MPa","value":"1.600","value_type":"decimal"},{"unit":null,"value":"1e0","value_type":"decimal"}]'),
    vector("nested_arrays", {"b":[[{},None],{"z":False,"a":[1,"x"]}],"a":{"z":[],"a":{}}}, '{"a":{"a":{},"z":[]},"b":[[{},null],{"a":[1,"x"],"z":false}]}'),
    vector("uuid_datetime_module_parents", {"id":"00000000-0000-4000-8000-000000000001", "created_at":"0001-01-01T00:00:00.000Z", "module_snapshot_hash":"a"*64,"parents":["b"*64,"c"*64]}, '{"created_at":"0001-01-01T00:00:00.000Z","id":"00000000-0000-4000-8000-000000000001","module_snapshot_hash":"'+"a"*64+'","parents":["'+"b"*64+'","'+"c"*64+'"]}'),
]
vectors.extend([
    vector("null",None,'null'), vector("true",True,'true'), vector("false",False,'false'),
    vector("empty_string","",'""'), vector("empty_array",[],'[]'), vector("empty_object",{},'{}'),
    vector("zero",0,'0'), vector("negative_integer",-12,'-12'),
    vector("chinese","科研",'"科研"'), vector("emoji","😀",'"😀"'),
    vector("combining","e\u0301",'"é"'), vector("decimal_1_60",{"value_type":"decimal","value":"1.60"},'{"value":"1.60","value_type":"decimal"}'),
    vector("decimal_1_600",{"value_type":"decimal","value":"1.600"},'{"value":"1.600","value_type":"decimal"}'),
    vector("scientific_9e18",{"value_type":"decimal","value":"9e18"},'{"value":"9e18","value_type":"decimal"}'),
])

nested = 0
for _ in range(64):
    nested = [nested]
vectors.append(vector("maximum_nesting_64", nested, "[" * 64 + "0" + "]" * 64))
nesting_cases = [
    {"name": f"nesting_{depth}", "depth": depth, "valid": depth <= 64,
     "raw": "[" * depth + "0" + "]" * depth}
    for depth in [64, 65, 600]
]


def uid(n):
    return f"00000000-0000-4000-8000-{n:012d}"


base = {"transaction_id": uid(1), "idempotency_key": uid(1), "project_id": uid(2), "device_id": uid(3), "actor_id": uid(4), "actor_type": "human", "protocol_version": 1, "schema_version": 1, "created_at": "2026-10-07T01:02:03.004Z", "ordered_change_ids": [uid(5), uid(8)], "dependencies": []}
common = {key: base[key] for key in ["transaction_id", "project_id", "device_id", "actor_id", "actor_type", "schema_version", "created_at"]}
first = dict(common, change_id=uid(5), audit_id=uid(6), object_type="Parameter", object_id=uid(7), operation="create", parents=[], payload={"name":"pressure", "value_type":"decimal", "value":"1.60", "unit":"MPa"}, module_snapshot_hash="a"*64)
second = dict(common, change_id=uid(8), audit_id=uid(9), object_type="Metric", object_id=uid(10), operation="update", parents=["b"*64], payload={"name":"IoU","value_type":"decimal","value":"0.900","status":"simulated"}, module_snapshot_hash="a"*64)
base["changes"] = [first, second]

# Handwritten key order and payload text are the independent anchor for full changes.
def anchor_change(change, payload_anchor, parents_anchor):
    return ('{"actor_id":"'+change["actor_id"]+'","actor_type":"'+change["actor_type"]+'","audit_id":"'+change["audit_id"]+'","change_id":"'+change["change_id"]+'","created_at":"'+change["created_at"]+'","device_id":"'+change["device_id"]+'","module_snapshot_hash":"'+change["module_snapshot_hash"]+'","object_id":"'+change["object_id"]+'","object_type":"'+change["object_type"]+'","operation":"'+change["operation"]+'","parents":'+parents_anchor+',"payload":'+payload_anchor+',"project_id":"'+change["project_id"]+'","schema_version":1,"transaction_id":"'+change["transaction_id"]+'"}')


c1 = anchor_change(first, '{"name":"pressure","unit":"MPa","value":"1.60","value_type":"decimal"}', '[]')
c2 = anchor_change(second, '{"name":"IoU","status":"simulated","value":"0.900","value_type":"decimal"}', '["'+"b"*64+'"]')
tx_anchor = ('{"actor_id":"'+uid(4)+'","actor_type":"human","changes":['+c1+','+c2+'],"created_at":"2026-10-07T01:02:03.004Z","dependencies":[],"device_id":"'+uid(3)+'","idempotency_key":"'+uid(1)+'","ordered_change_ids":["'+uid(5)+'","'+uid(8)+'"],"project_id":"'+uid(2)+'","protocol_version":1,"schema_version":1,"transaction_id":"'+uid(1)+'"}')
vectors.extend([vector("semantic_change", first, c1), vector("multi_changes_transaction", base, tx_anchor)])
valid = {"name": "multi_change_valid", "valid": True, "raw": json.dumps(base, ensure_ascii=False), "digest": hashlib.sha256(tx_anchor.encode()).hexdigest(), "revisions": [hashlib.sha256(c.encode()).hexdigest() for c in [c1,c2]]}
cases = [valid]


def valid_variant(name, payload, payload_anchor, operation="create", parents=None, dependencies=None, created_at=None):
    tx = copy.deepcopy(base)
    change = tx["changes"][0]
    change["payload"] = payload
    change["operation"] = operation
    change["parents"] = parents or []
    if created_at:
        tx["created_at"] = created_at
        change["created_at"] = created_at
    tx["changes"] = [change]
    tx["ordered_change_ids"] = [change["change_id"]]
    tx["dependencies"] = dependencies or []
    parent_anchor = '['+','.join('"'+p+'"' for p in change["parents"])+']'
    change_anchor = anchor_change(change,payload_anchor,parent_anchor)
    dependencies_anchor = '['+','.join('"'+p+'"' for p in tx["dependencies"])+']'
    anchor = ('{"actor_id":"'+uid(4)+'","actor_type":"human","changes":['+change_anchor+'],"created_at":"'+tx["created_at"]+'","dependencies":'+dependencies_anchor+',"device_id":"'+uid(3)+'","idempotency_key":"'+uid(1)+'","ordered_change_ids":["'+uid(5)+'"],"project_id":"'+uid(2)+'","protocol_version":1,"schema_version":1,"transaction_id":"'+uid(1)+'"}')
    cases.append({"name": name,"valid": True,"raw": json.dumps(tx,ensure_ascii=False),"digest": hashlib.sha256(anchor.encode()).hexdigest(),"revisions": [hashlib.sha256(change_anchor.encode()).hexdigest()]})


valid_variant("unknown_scientific_null",{"name":"pressure","status":"unknown","unit":None,"value":None,"value_type":"decimal"},'{"name":"pressure","status":"unknown","unit":null,"value":null,"value_type":"decimal"}')
valid_variant("exact_large_integer",{"name":"count","value":"9000000000000000000","value_type":"integer"},'{"name":"count","value":"9000000000000000000","value_type":"integer"}')
valid_variant("resolve_multiple_heads",{"name":"pressure","value":"1.600","value_type":"decimal"},'{"name":"pressure","value":"1.600","value_type":"decimal"}',"resolve",["b"*64,"c"*64],[uid(20),uid(21)])
valid_variant("resolve_single_batch_member",{"name":"pressure"},'{"name":"pressure"}',"resolve",["b"*64])
valid_variant("first_calendar_year",{},'{}',created_at="0001-01-01T00:00:00.000Z")
valid_variant("last_calendar_year",{},'{}',created_at="9999-12-31T23:59:59.999Z")


def invalid(name, mutate=None, raw=None, context=None):
    tx = copy.deepcopy(base)
    if mutate:
        mutate(tx)
    result = {"name": name, "valid": False, "raw": raw or json.dumps(tx, ensure_ascii=False)}
    if context:
        result["context"] = context
    cases.append(result)


def change_field(key,value):
    return lambda tx: tx["changes"][0].__setitem__(key,value)


for name, mutate in [
    ("unknown_tx_field", lambda t:t.update(state="ACCEPTED")),
    ("unknown_change_field", change_field("revision", "a"*64)),
    ("unknown_payload_field", lambda t:t["changes"][0]["payload"].update(secret="x")),
    ("unknown_protocol", lambda t:t.update(protocol_version=2)),
    ("unknown_schema", lambda t:t.update(schema_version=2)),
    ("boolean_version", lambda t:t.update(protocol_version=True)),
    ("uppercase_uuid", lambda t:t.update(actor_id="FFFFFFFF-FFFF-4FFF-8FFF-FFFFFFFFFFFF")),
    ("nil_uuid", lambda t:t.update(actor_id="00000000-0000-0000-0000-000000000000")),
    ("cross_project", change_field("project_id",uid(99))),
    ("different_actor", change_field("actor_type","codex")),
    ("idempotency_mismatch",lambda t:t.update(idempotency_key=uid(99))),
    ("ordered_ids_mismatch",lambda t:t.update(ordered_change_ids=list(reversed(t["ordered_change_ids"])))),
    ("duplicate_object",lambda t:t["changes"][1].update(object_type="Parameter",object_id=uid(7))),
    ("duplicate_audit",lambda t:t["changes"][1].update(audit_id=uid(6))),
    ("duplicate_changes",lambda t:t.update(changes=[first,first],ordered_change_ids=[uid(5),uid(5)])),
    ("empty_changes",lambda t:t.update(changes=[],ordered_change_ids=[])),
    ("bad_module_digest",change_field("module_snapshot_hash","A"*64)),
    ("native_decimal_value",lambda t:t["changes"][0]["payload"].update(value=1)),
    ("bad_decimal_grammar",lambda t:t["changes"][0]["payload"].update(value="01.60")),
    ("decimal_trailing_newline",lambda t:t["changes"][0]["payload"].update(value="1.60\n")),
    ("integer_trailing_newline",lambda t:t["changes"][0]["payload"].update(value_type="integer",value="16\n")),
    ("uuid_trailing_newline",lambda t:t.update(actor_id=uid(4)+"\n")),
    ("module_hash_trailing_newline",change_field("module_snapshot_hash","a"*64+"\n")),
    ("decimal_exponent_limit",lambda t:t["changes"][0]["payload"].update(value="1e100001")),
    ("tagged_integer_negative_zero",lambda t:t["changes"][0]["payload"].update(value_type="integer",value="-0")),
    ("type_mismatch",lambda t:t["changes"][0]["payload"].update(is_confirmed="yes")),
    ("unknown_status",lambda t:t["changes"][1]["payload"].update(status="ready")),
    ("invalid_artifact_sync_policy",lambda t:t["changes"][0].update(object_type="Artifact",payload={"sync_policy":"public"})),
    ("invalid_artifact_origin_uuid",lambda t:t["changes"][0].update(object_type="Artifact",payload={"origin_device":"primary"})),
    ("purge_rejected",change_field("operation","purge")),
    ("unknown_object_type",change_field("object_type","User")),
    ("create_has_parent",change_field("parents",["a"*64])),
    ("update_no_parent",lambda t:t["changes"][1].update(parents=[])),
    ("unsorted_parents",lambda t:t["changes"][1].update(operation="resolve",parents=["c"*64,"b"*64])),
    ("duplicate_parents",lambda t:t["changes"][1].update(operation="resolve",parents=["b"*64,"b"*64])),
    ("unsorted_dependencies",lambda t:t.update(dependencies=[uid(20),uid(19)])),
    ("self_dependency",lambda t:t.update(dependencies=[uid(1)])),
    ("duplicate_dependencies",lambda t:t.update(dependencies=[uid(20),uid(20)])),
]:
    invalid(name,mutate)
for stamp in ["2026-02-29T00:00:00.000Z","2026-10-07T01:02:03Z","2026-10-07T01:02:03.000+00:00","0000-01-01T00:00:00.000Z","2026-10-07T01:02:60.000Z"]:
    invalid("datetime_"+stamp,lambda t,s=stamp:t.update(created_at=s))
for raw in ['{"x":1,"\\u0078":2}', '-0', '1.0', '1e0', '9007199254740992']:
    invalid("raw_"+raw,raw=raw)
for field,value in [("actor_type","codex"),("actor_id",uid(99)),("device_id",uid(99)),("project_id",uid(99))]:
    invalid("context_"+field,context={field:value})
DEST.joinpath("canonical.json").write_text(json.dumps(vectors,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
DEST.joinpath("protocol.json").write_text(json.dumps(cases,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
DEST.joinpath("nesting.json").write_text(json.dumps(nesting_cases, indent=2)+"\n", encoding="utf-8")
