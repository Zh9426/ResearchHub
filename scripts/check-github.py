"""通过既有 Git Credential Manager 验证仓库隐私；从不打印认证值。"""
import argparse
import subprocess

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--ensure-private", action="store_true")
parser.add_argument("--ci", action="store_true", help="读取当前分支最新 Actions 检查状态")
args = parser.parse_args()
result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                        text=True, capture_output=True, check=True)
credentials = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
token = credentials.get("password")
if not token:
    raise RuntimeError("GitHub 本机认证不可用")
with httpx.Client(headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                           "X-GitHub-Api-Version": "2022-11-28"}, timeout=30) as client:
    url = "https://api.github.com/repos/Zh9426/ResearchHub"
    response = client.get(url)
    response.raise_for_status()
    repo = response.json()
    if not repo.get("private") and args.ensure_private:
        response = client.patch(url, json={"private": True})
        response.raise_for_status()
        repo = client.get(url).raise_for_status().json()
    if not repo.get("private"):
        raise RuntimeError("仓库并非私有，暂停推送")
    print("Verified: Zh9426/ResearchHub private=true, visibility=" + repo.get("visibility", "unknown"))

    if args.ci:
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip()
        runs = client.get(url + "/actions/runs", params={"branch": branch, "per_page": 3}).raise_for_status().json()
        for run in runs.get("workflow_runs", []):
            print("CI:", run["head_sha"], run["status"], run.get("conclusion"), run["html_url"])
        if not runs.get("workflow_runs"):
            print("CI: no remote workflow run yet")
