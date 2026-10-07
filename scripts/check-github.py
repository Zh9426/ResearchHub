"""通过既有 Git Credential Manager 只读检查仓库与 CI；从不打印认证值。"""

import argparse
import subprocess

import httpx


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读检查 GitHub 仓库可见性与 CI 状态")
    parser.add_argument(
        "--expect-visibility", choices=("public", "private"),
        help="可选的预期可见性；不匹配时失败，不修改仓库",
    )
    parser.add_argument("--ci", action="store_true", help="读取当前分支最新 Actions 检查状态")
    args = parser.parse_args(argv)
    result = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, check=True,
    )
    credentials = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    token = credentials.get("password")
    if not token:
        raise RuntimeError("GitHub 本机认证不可用")
    with httpx.Client(
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"}, timeout=30,
    ) as client:
        url = "https://api.github.com/repos/Zh9426/ResearchHub"
        response = client.get(url)
        response.raise_for_status()
        repo = response.json()
        visibility = repo.get("visibility", "private" if repo.get("private") else "public")
        if args.expect_visibility and visibility != args.expect_visibility:
            raise RuntimeError(f"仓库可见性不匹配：预期 {args.expect_visibility}，实际 {visibility}")
        print("Verified: Zh9426/ResearchHub visibility=" + visibility)

        if args.ci:
            branch = subprocess.run(
                ["git", "branch", "--show-current"], capture_output=True, text=True, check=True,
            ).stdout.strip()
            runs = client.get(
                url + "/actions/runs", params={"branch": branch, "per_page": 3},
            ).raise_for_status().json()
            for run in runs.get("workflow_runs", []):
                print("CI:", run["head_sha"], run["status"], run.get("conclusion"), run["html_url"])
            if not runs.get("workflow_runs"):
                print("CI: no remote workflow run yet")


if __name__ == "__main__":
    main()
