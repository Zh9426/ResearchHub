"""Real Codex host acceptance, restricted to the named disposable local QA deployment."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ACCEPTANCE_TOOLS = {
    'get_projects', 'create_run', 'upsert_run_parameters', 'save_run_metrics',
    'create_note', 'set_run_highlight', 'get_run',
}


def synthetic_zero(record, parameter=False):
    return (type(record.get('value')) in (int, float) and record['value'] == 0
            and record.get('unit') is None and record.get('source_kind') == 'synthetic'
            and (record.get('value_type') == 'number' and record.get('is_confirmed') is False
                 if parameter else record.get('status') == 'synthetic'))


def successful_tools(events, project_id, run_id):
    completed = set()
    for event in events:
        item = event.get('item', {})
        if event.get('type') != 'item.completed' or item.get('status') != 'completed' or item.get('error'):
            continue
        arguments = item.get('arguments', {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                continue
        tool = item.get('tool')
        if tool in {'create_run', 'create_note'} and arguments.get('project_id') != project_id:
            continue
        if tool in {'upsert_run_parameters', 'save_run_metrics', 'set_run_highlight', 'get_run'} and arguments.get('run_id') != run_id:
            continue
        completed.add(tool)
    return completed


def revoke_token(owner, token_id):
    errors = []
    for _ in range(3):
        try:
            response = owner.delete(f'/api/auth/tokens/{token_id}')
            if response.status_code in (200, 404):
                return True, errors
            errors.append(f'HTTP {response.status_code}')
        except httpx.RequestError as error:
            errors.append(type(error).__name__)
    return False, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codex', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime = root / 'storage' / 'runtime'
    credentials = json.loads((runtime / 'docker-qa-credentials.json').read_text(encoding='utf-8-sig'))
    url = 'http://127.0.0.1:3300'
    marker = uuid4().hex[:8]
    report = {'status': 'NOT VERIFIED', 'target': url, 'marker': marker}
    with httpx.Client(base_url=url, trust_env=False, timeout=30) as owner:
        login = owner.post('/api/auth/login', json=credentials).raise_for_status().json()
        owner.headers['X-CSRF-Token'] = login['csrf_token']
        project = owner.post('/api/projects', json={
            'name': f'SYNTHETIC Codex host {marker}', 'module_id': 'generic',
            'description': '真实 Codex 客户端软件验收，全部数值为合成值，不是科研结果。',
            'repository': 'https://github.com/Zh9426/ResearchHub',
        }).raise_for_status().json()
        token = owner.post('/api/auth/tokens', json={
            'name': f'SYNTHETIC temporary Codex host {marker}',
            'actor_type': 'codex', 'scopes': ['research:read', 'research:write'],
        }).raise_for_status().json()
        report['project_id'] = project['id']
        try:
            prompt = f'''这是已授权的隔离 Research Hub 软件验收，只操作项目 {project['id']}。
仅使用 research_hub MCP 工具，不调用 shell、浏览器或读写工作区文件。
1. get_projects 查询项目，q 使用 SYNTHETIC Codex host {marker}，确认目标。
2. create_run 创建 simulation 类型记录，标题 SYNTHETIC Codex 真实连接 {marker}，目标说明软件验收，不代表科研事实。
3. upsert_run_parameters 保存 qa_input=0（number，unit=null，source_kind=synthetic，is_confirmed=false），保持未知单位，不写人工确认。
4. save_run_metrics 保存 qa_output=0（unit=null，status=synthetic，source_kind=synthetic）。
5. create_note 添加关联记录笔记，明确这里只验证客户端至本地服务连接。
6. 我明确请求把刚创建的记录设为星标，reason 为 SYNTHETIC 客户端验收，user_requested=true。
7. get_run 读回，确认参数、指标、笔记/星标保存。不要写人工结论、通过关卡、接受决策或验证科学证据。
最终只返回 JSON，含 project_id、run_id、note_id 和成功步骤；如失败如实说明，不编造成功。
'''
            server = {
                'command': str(root / '.venv' / 'Scripts' / 'python.exe'),
                'args': [str(root / 'scripts' / 'mcp-local.py')],
                'cwd': str(root),
                'env_vars': ['RESEARCHHUB_API_URL', 'RESEARCHHUB_API_TOKEN'],
                'startup_timeout_sec': 30,
                'enabled_tools': sorted(ACCEPTANCE_TOOLS),
            }
            # JSON string literals are valid TOML basic strings; no shell is invoked.
            table = '{' + ','.join(f'{key}={json.dumps(value)}' for key, value in server.items()) + '}'
            env = {**os.environ, 'RESEARCHHUB_API_URL': url, 'RESEARCHHUB_API_TOKEN': token['token']}
            events_path = runtime / f'codex-host-{marker}.jsonl'
            error_path = runtime / f'codex-host-{marker}.stderr.log'
            final_path = runtime / f'codex-host-{marker}-final.txt'
            command = [str(args.codex), 'exec', '--ignore-user-config', '--ephemeral',
                       '--json', '-s', 'read-only', '-C', str(root),
                       '-c', f'mcp_servers.research_hub={table}',
                       '-o', str(final_path), '-']
            # Only this run's seven explicitly requested QA tools are preapproved.
            for tool in sorted(ACCEPTANCE_TOOLS):
                command[-3:-3] = ['-c', f'mcp_servers.research_hub.tools.{tool}.approval_mode="approve"']
            start = time.monotonic()
            with events_path.open('w', encoding='utf-8') as out, error_path.open('w', encoding='utf-8') as err:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err, env=env)
                try:
                    process.communicate(prompt.encode('utf-8'), timeout=300)
                    report['exit_code'] = process.returncode
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    report['error'] = 'Real Codex execution timed out after 300 seconds.'
            report['elapsed_seconds'] = round(time.monotonic() - start, 2)
            events = []
            for line in events_path.read_text(encoding='utf-8').splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            report['mcp_events'] = [event for event in events if 'mcp_tool_call' in str(event.get('item', {}).get('type', ''))]
            report['event_errors'] = [event for event in events if event.get('type') == 'error']
            runs = owner.get(f"/api/projects/{project['id']}/runs/query").raise_for_status().json()['items']
            matching = [run for run in runs if marker in run['title']]
            if len(matching) == 1:
                run = matching[0]
                report['run_id'] = run['id']
                context = owner.get(f"/api/runs/{run['id']}/context").raise_for_status().json()
                notes = owner.get(f"/api/projects/{project['id']}/notes/query").raise_for_status().json()['items']
                activity = owner.get(f"/api/audit?project_id={project['id']}&format=page&limit=100&range=all").raise_for_status().json()
                entries = activity['items'] if isinstance(activity, dict) else activity
                audit = [entry for entry in entries if entry.get('actor_type') == 'codex']
                report['audit'] = audit
                report['checks'] = {
                    'parameter_zero': any(p['name'] == 'qa_input' and synthetic_zero(p, parameter=True) for p in context['parameters']),
                    'metric_zero': any(m['name'] == 'qa_output' and synthetic_zero(m) for m in context['metrics']),
                    'note': any(note.get('run_id') == run['id'] for note in notes),
                    'highlight': bool(run.get('is_highlighted')),
                    'codex_audit': len(audit) >= 5 and all(entry.get('source') == 'mcp' for entry in audit),
                    'human_conclusion_empty': not run.get('human_conclusion'),
                    'actual_mcp_events': ACCEPTANCE_TOOLS <= successful_tools(report['mcp_events'], project['id'], run['id']),
                }
            report['artifacts'] = {'events': str(events_path.relative_to(root)), 'stderr': str(error_path.relative_to(root)), 'final': str(final_path.relative_to(root))}
        except Exception as error:  # noqa: BLE001 - preserve diagnostic report and revoke token on any host failure
            report['error'] = type(error).__name__
        finally:
            report['token_revoked'], report['cleanup_errors'] = revoke_token(owner, token['id'])
            if not report['token_revoked']:
                report['token_id_to_revoke'] = token['id']
            if report.get('exit_code') == 0 and report.get('checks') and all(report['checks'].values()) and report['token_revoked']:
                report['status'] = 'TESTED'
            report_path = runtime / 'codex-host-acceptance.json'
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: value for key, value in report.items() if key not in ('mcp_events', 'audit')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
