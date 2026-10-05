"""Stdio MCP server. API enforces token scopes, ownership and audited actor."""
import os

from apps.mcp.adapter import ResearchHubClient
from mcp.server.fastmcp import FastMCP


def build_server(client: ResearchHubClient) -> FastMCP:
    server = FastMCP('Research Hub', instructions='Research Hub is the source of research facts. Preserve unknown/synthetic evidence boundaries; write tools create audit records.')

    @server.tool()
    async def get_projects() -> list[dict]:
        """List the authenticated owner's research projects."""
        return await client.get_projects()

    @server.tool()
    async def get_project(project_id: str) -> dict:
        """Read one owned project by UUID."""
        return await client.get_project(project_id)

    @server.tool()
    async def get_project_context(project_id: str) -> dict:
        """Read project workflow, runs, evidence and decisions with provenance."""
        return await client.get_project_context(project_id)

    @server.tool()
    async def list_runs(project_id: str) -> list[dict]:
        """List owned project research runs."""
        return await client.list_runs(project_id)

    @server.tool()
    async def get_run(run_id: str) -> dict:
        """Read a run with parameters, metrics, artifacts, parent and children."""
        return await client.get_run(run_id)

    @server.tool()
    async def create_run(project_id: str, run: dict) -> dict:
        """Create a research run. Requires research:write; include title and module run_type."""
        return await client.create_run(project_id, run)

    @server.tool()
    async def save_run_metrics(run_id: str, metrics: list[dict]) -> list[dict]:
        """Atomically save 1–100 metrics with name/value/unit/status. Requires research:write."""
        return await client.save_run_metrics(run_id, metrics)

    @server.tool()
    async def create_note(project_id: str, title: str, content: str, run_id: str | None = None) -> dict:
        """Create a note, optionally linked to a run. Requires research:write."""
        return await client.create_note(project_id, title, content, run_id)

    @server.tool()
    async def create_task(project_id: str, title: str, description: str = '', priority: str = 'medium') -> dict:
        """Create a todo task. Requires research:write."""
        return await client.create_task(project_id, title, description, priority)

    return server


def main():
    client = ResearchHubClient(os.environ.get('RESEARCHHUB_API_URL', 'http://localhost:3000'), os.environ.get('RESEARCHHUB_API_TOKEN', ''))
    build_server(client).run(transport='stdio')


if __name__ == '__main__':
    main()
