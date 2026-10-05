"""Only explicit application operations; never DB, shell or arbitrary paths."""
from urllib.parse import urlparse
from uuid import UUID

import httpx


class ResearchHubClient:
    def __init__(self, base_url: str, token: str, transport=None):
        parsed = urlparse(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use an http(s) API URL without embedded credentials')
        if not token or not token.strip():
            raise ValueError('Research Hub API token is required')
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.transport = transport

    @staticmethod
    def _id(value: str) -> str:
        return str(UUID(value))

    async def _request(self, method: str, path: str, body=None):
        async with httpx.AsyncClient(
            base_url=self.base_url, headers={'Authorization': f'Bearer {self.token}'},
            timeout=30, follow_redirects=False, transport=self.transport,
        ) as client:
            try:
                response = await client.request(method, '/api' + path, json=body)
            except httpx.RequestError:
                raise RuntimeError('Research Hub API unavailable; check server and configured URL') from None
        if response.status_code in (401, 403):
            raise PermissionError(f'Research Hub denied request ({response.status_code}); check token scope and ownership')
        if not response.is_success:
            raise RuntimeError(f'Research Hub API rejected request ({response.status_code}); inspect server audit/logs')
        return response.json() if response.content else None

    async def get_projects(self):
        return await self._request('GET', '/projects')

    async def get_project(self, project_id: str):
        return await self._request('GET', f'/projects/{self._id(project_id)}')

    async def get_project_context(self, project_id: str):
        return await self._request('GET', f'/projects/{self._id(project_id)}/context')

    async def list_runs(self, project_id: str):
        return await self._request('GET', f'/projects/{self._id(project_id)}/runs')

    async def get_run(self, run_id: str):
        return await self._request('GET', f'/runs/{self._id(run_id)}/context')

    async def create_run(self, project_id: str, run: dict):
        return await self._request('POST', f'/projects/{self._id(project_id)}/runs', run)

    async def save_run_metrics(self, run_id: str, metrics: list[dict]):
        if not metrics or len(metrics) > 100:
            raise ValueError('Provide between 1 and 100 metrics')
        return await self._request('POST', f'/runs/{self._id(run_id)}/metrics/batch', {'metrics': metrics})

    async def create_note(self, project_id: str, title: str, content: str, run_id: str | None = None):
        return await self._request('POST', f'/projects/{self._id(project_id)}/notes', {
            'title': title, 'content': content, 'run_id': self._id(run_id) if run_id else None,
        })

    async def create_task(self, project_id: str, title: str, description: str = '', priority: str = 'medium'):
        return await self._request('POST', f'/projects/{self._id(project_id)}/tasks', {
            'title': title, 'description': description, 'priority': priority, 'status': 'todo',
        })
