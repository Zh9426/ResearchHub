"""Stdio MCP server. API enforces scopes, ownership, lifecycle and actor audits."""

import os

from apps.mcp.adapter import ResearchHubClient
from mcp.server.fastmcp import FastMCP


def build_server(client: ResearchHubClient) -> FastMCP:
    server = FastMCP(
        "Research Hub",
        instructions="Research Hub stores research facts. AI writes are proposals; never confirm parameters, validate evidence/metrics, supply human conclusions or pass gates. Highlight changes require an explicit user request. All collection reads are paged; total describes the entire matching collection. GitHub links are saved code provenance only. No SQL, shell or arbitrary server files.",
    )

    @server.tool()
    async def get_projects(limit: int = 50, offset: int = 0, q: str = "") -> dict:
        """Page active owned projects as items/total/limit/offset (limit 1–100)."""
        return await client.get_projects(limit, offset, q)

    @server.tool()
    async def get_project_summary(
        project_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """Read project/module/counts and individually paged groups of Runs/tasks/gates/risks/decisions."""
        return await client.get_project_summary(project_id, limit, offset)

    @server.tool()
    async def search_research(
        q: str,
        project_id: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Page text matches in owned active projects; optional UUID project scope and collection kind."""
        return await client.search_research(q, project_id, kind, limit, offset)

    @server.tool()
    async def query_runs(
        project_id: str,
        q: str = "",
        filters: dict | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Page owned Runs. filters: run_type/status/scientific_outcome/tag_id/parent_run_id/is_highlighted/date_from/date_to/sort/direction. q is text search."""
        return await client.query_runs(project_id, q, filters, limit, offset)

    @server.tool()
    async def get_run(run_id: str, limit: int = 50, offset: int = 0) -> dict:
        """Read {run,parent,groups}. Each parameters/metrics/artifacts/referenced_artifacts/evidence/notes/children group has items,total,limit,offset."""
        return await client.get_run(run_id, limit, offset)

    @server.tool()
    async def compare_runs(
        run_id: str, other_run_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """Compare active Runs in one project: current/other saved code provenance plus paged parameter and metric diffs."""
        return await client.compare_runs(run_id, other_run_id, limit, offset)

    @server.tool()
    async def get_highlighted_runs(
        project_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """Page starred owned Runs; a star does not validate a scientific result."""
        return await client.get_highlighted_runs(project_id, limit, offset)

    @server.tool()
    async def get_current_blockers(
        project_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """Page blocked Runs/tasks/milestones, blocked/failed gates and open risks with their saved descriptions."""
        return await client.get_current_blockers(project_id, limit, offset)

    @server.tool()
    async def get_evidence_trace(
        project_id: str, kind: str, resource_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """Trace a project resource to individually paged evidence/support groups. kind: claims/evidence/runs/artifacts/sources/parameters/metrics/gates/criteria/decisions."""
        return await client.get_evidence_trace(
            project_id, kind, resource_id, limit, offset
        )

    @server.tool()
    async def create_run(project_id: str, run: dict) -> dict:
        """Create a Run with title/run_type and optional provenance/context. AI cannot write human_conclusion."""
        return await client.create_run(project_id, run)

    @server.tool()
    async def clone_run(run_id: str, clone: dict) -> dict:
        """Create a child Run; clone requires title and optional inheritance flags. Confirmation/results/highlights are not inherited."""
        return await client.clone_run(run_id, clone)

    @server.tool()
    async def upsert_run_parameters(run_id: str, parameters: list[dict]) -> list[dict]:
        """Atomically upsert 1–100 named parameters; AI cannot confirm or change confirmed values."""
        return await client.upsert_run_parameters(run_id, parameters)

    @server.tool()
    async def save_run_metrics(run_id: str, metrics: list[dict]) -> list[dict]:
        """Atomically save 1–100 metrics; AI cannot mark validated/reproduced or change already validated metrics."""
        return await client.save_run_metrics(run_id, metrics)

    @server.tool()
    async def create_note(
        project_id: str, title: str, content: str, run_id: str | None = None
    ) -> dict:
        """Create an owned project note, optionally linked to an owned Run."""
        return await client.create_note(project_id, title, content, run_id)

    @server.tool()
    async def create_task(
        project_id: str, title: str, description: str = "", priority: str = "medium"
    ) -> dict:
        """Create a todo task. Requires research:write."""
        return await client.create_task(project_id, title, description, priority)

    @server.tool()
    async def register_artifact(run_id: str, file_id: str) -> dict:
        """Reference an existing active owned project file in a Run. IDs only; no server paths, arbitrary URLs or filesystem reads."""
        return await client.register_artifact(run_id, file_id)

    @server.tool()
    async def create_proposed_evidence(project_id: str, evidence: dict) -> dict:
        """Create proposed evidence with title/description/type/limitations and owned links. Status is always proposed."""
        return await client.create_proposed_evidence(project_id, evidence)

    @server.tool()
    async def set_run_highlight(
        run_id: str,
        is_highlighted: bool,
        user_requested: bool = False,
        type: str | None = None,
        note: str = "",
    ) -> dict:
        """Change a Run star ONLY after the user explicitly asks; user_requested=true is required. Star is independent of evidence status."""
        return await client.set_run_highlight(
            run_id, is_highlighted, user_requested, type, note
        )

    @server.tool()
    async def get_project(project_id: str) -> dict:
        """Compatibility alias: read one active owned project by UUID."""
        return await client.get_project(project_id)

    @server.tool()
    async def get_project_context(
        project_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """Compatibility alias for the bounded project summary with paged groups."""
        return await client.get_project_context(project_id, limit, offset)

    @server.tool()
    async def list_runs(project_id: str, limit: int = 50, offset: int = 0) -> dict:
        """Compatibility alias for paged query_runs."""
        return await client.list_runs(project_id, limit, offset)

    return server


def main():
    client = ResearchHubClient(
        os.environ.get("RESEARCHHUB_API_URL", "http://localhost:3000"),
        os.environ.get("RESEARCHHUB_API_TOKEN", ""),
    )
    build_server(client).run(transport="stdio")


if __name__ == "__main__":
    main()
