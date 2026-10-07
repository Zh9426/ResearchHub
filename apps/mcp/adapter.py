"""Only explicit application operations; never DB, shell or arbitrary paths."""

from urllib.parse import urlparse
from uuid import UUID

import httpx


class ResearchHubClient:
    def __init__(self, base_url: str, token: str, transport=None):
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Use an http(s) API URL without embedded credentials, query or fragment"
            )
        if not token or not token.strip():
            raise ValueError("Research Hub API token is required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport

    @staticmethod
    def _id(value: str) -> str:
        return str(UUID(value))

    @staticmethod
    def _page(limit=50, offset=0):
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            raise ValueError(
                "limit must be 1–100; offset must be a nonnegative integer"
            )
        return {"limit": limit, "offset": offset}

    async def _request(self, method: str, path: str, body=None, params=None):
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=30,
            follow_redirects=False,
            transport=self.transport,
            trust_env=False,
        ) as client:
            try:
                response = await client.request(
                    method, "/api" + path, json=body, params=params
                )
            except httpx.RequestError:
                raise RuntimeError(
                    "Research Hub API unavailable; check server and configured URL"
                ) from None
        if response.status_code in (401, 403):
            raise PermissionError(
                f"Research Hub denied request ({response.status_code}); check token scope and ownership"
            )
        if not response.is_success:
            raise RuntimeError(
                f"Research Hub API rejected request ({response.status_code}); inspect server audit/logs"
            )
        return response.json() if response.content else None

    async def get_projects(self, limit=50, offset=0, q=""):
        return await self._request(
            "GET",
            "/projects",
            params={**self._page(limit, offset), "format": "page", "q": q[:300]},
        )

    async def get_project(self, project_id: str):
        summary = await self.get_project_summary(project_id, limit=1)
        return summary["project"]

    async def get_project_summary(self, project_id: str, limit=50, offset=0):
        return await self._request(
            "GET",
            f"/projects/{self._id(project_id)}/summary",
            params={**self._page(limit, offset), "format": "page"},
        )

    async def get_project_context(self, project_id: str, limit=50, offset=0):
        return await self.get_project_summary(project_id, limit, offset)

    async def search_research(
        self,
        q: str,
        project_id: str | None = None,
        kind: str | None = None,
        limit=50,
        offset=0,
    ):
        params = {**self._page(limit, offset), "q": q[:300]}
        if project_id:
            params["project_id"] = self._id(project_id)
        if kind:
            params["kind"] = kind
        return await self._request("GET", "/search", params=params)

    async def query_runs(
        self, project_id: str, q="", filters: dict | None = None, limit=50, offset=0
    ):
        filters = filters or {}
        allowed = {
            "run_type",
            "status",
            "scientific_outcome",
            "tag_id",
            "parent_run_id",
            "is_highlighted",
            "date_from",
            "date_to",
            "sort",
            "direction",
        }
        if not set(filters) <= allowed:
            raise ValueError("Unsupported Run query filter")
        for key in ("tag_id", "parent_run_id"):
            if filters.get(key) and filters[key] != "null":
                filters = {**filters, key: self._id(filters[key])}
        if isinstance(filters.get("is_highlighted"), bool):
            filters = {
                **filters,
                "is_highlighted": str(filters["is_highlighted"]).lower(),
            }
        return await self._request(
            "GET",
            f"/projects/{self._id(project_id)}/runs/query",
            params={
                **filters,
                **self._page(limit, offset),
                "q": q[:300],
                "active_only": "true",
            },
        )

    async def list_runs(self, project_id: str, limit=50, offset=0):
        return await self.query_runs(project_id, limit=limit, offset=offset)

    async def get_run(self, run_id: str, limit=50, offset=0):
        return await self._request(
            "GET",
            f"/runs/{self._id(run_id)}/context",
            params={**self._page(limit, offset), "format": "page"},
        )

    async def compare_runs(self, run_id: str, other_run_id: str, limit=50, offset=0):
        return await self._request(
            "GET",
            f"/runs/{self._id(run_id)}/compare",
            params={
                **self._page(limit, offset),
                "other_run_id": self._id(other_run_id),
            },
        )

    async def get_highlighted_runs(self, project_id: str, limit=50, offset=0):
        return await self.query_runs(
            project_id, filters={"is_highlighted": True}, limit=limit, offset=offset
        )

    async def get_current_blockers(self, project_id: str, limit=50, offset=0):
        return await self._request(
            "GET",
            f"/projects/{self._id(project_id)}/blockers",
            params=self._page(limit, offset),
        )

    async def get_evidence_trace(
        self, project_id: str, kind: str, resource_id: str, limit=50, offset=0
    ):
        if kind not in {
            "claims",
            "evidence",
            "runs",
            "artifacts",
            "sources",
            "parameters",
            "metrics",
            "gates",
            "criteria",
            "decisions",
        }:
            raise ValueError("Unsupported evidence trace subject")
        return await self._request(
            "GET",
            f"/projects/{self._id(project_id)}/evidence-trace/{kind}/{self._id(resource_id)}",
            params=self._page(limit, offset),
        )

    async def create_run(self, project_id: str, run: dict):
        return await self._request(
            "POST", f"/projects/{self._id(project_id)}/runs", run
        )

    async def clone_run(self, run_id: str, clone: dict):
        return await self._request("POST", f"/runs/{self._id(run_id)}/clone", clone)

    async def upsert_run_parameters(self, run_id: str, parameters: list[dict]):
        if not parameters or len(parameters) > 100:
            raise ValueError("Provide between 1 and 100 parameters")
        return await self._request(
            "POST",
            f"/runs/{self._id(run_id)}/parameters/batch",
            {"parameters": parameters},
        )

    async def save_run_metrics(self, run_id: str, metrics: list[dict]):
        if not metrics or len(metrics) > 100:
            raise ValueError("Provide between 1 and 100 metrics")
        return await self._request(
            "POST", f"/runs/{self._id(run_id)}/metrics/batch", {"metrics": metrics}
        )

    async def create_note(
        self, project_id: str, title: str, content: str, run_id: str | None = None
    ):
        return await self._request(
            "POST",
            f"/projects/{self._id(project_id)}/notes",
            {
                "title": title,
                "content": content,
                "run_id": self._id(run_id) if run_id else None,
            },
        )

    async def create_task(
        self,
        project_id: str,
        title: str,
        description: str = "",
        priority: str = "medium",
    ):
        return await self._request(
            "POST",
            f"/projects/{self._id(project_id)}/tasks",
            {
                "title": title,
                "description": description,
                "priority": priority,
                "status": "todo",
            },
        )

    async def register_artifact(self, run_id: str, file_id: str):
        return await self._request(
            "POST",
            f"/runs/{self._id(run_id)}/artifacts/register",
            {"file_id": self._id(file_id)},
        )

    async def create_proposed_evidence(self, project_id: str, evidence: dict):
        if "status" in evidence and evidence["status"] != "proposed":
            raise ValueError("AI evidence must remain proposed")
        return await self._request(
            "POST",
            f"/projects/{self._id(project_id)}/evidence",
            {**evidence, "status": "proposed"},
        )

    async def set_run_highlight(
        self,
        run_id: str,
        is_highlighted: bool,
        user_requested: bool = False,
        type: str | None = None,
        note: str = "",
    ):
        if user_requested is not True:
            raise PermissionError(
                "Highlight changes require an explicit user request (user_requested=true)"
            )
        return await self._request(
            "PATCH",
            f"/runs/{self._id(run_id)}/highlight",
            {
                "is_highlighted": is_highlighted,
                "user_requested": True,
                "type": type,
                "note": note,
            },
        )
