"""生成被忽略的隔离 QA 配置，绝不打印凭据。"""
import argparse
import json
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--replace-invalid", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
target = root / ".env.qa"
if target.exists() and not args.replace_invalid:
    print("QA 配置已存在，保留原值。")
else:
    values = {
        "POSTGRES_DB": "researchhub_qa", "POSTGRES_USER": "researchhub",
        "POSTGRES_PASSWORD": secrets.token_hex(32), "S3_ACCESS_KEY": "rhqa" + secrets.token_hex(8),
        "S3_SECRET_KEY": secrets.token_hex(32), "S3_BUCKET": "researchhub-qa",
        "COOKIE_SECURE": "false", "CORS_ORIGINS": "http://localhost:3300,http://127.0.0.1:3300",
        "MAX_UPLOAD_BYTES": "104857600",
    }
    target.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    credentials = root / "storage/runtime/docker-qa-credentials.json"
    credentials.parent.mkdir(parents=True, exist_ok=True)
    if not credentials.exists():
        credentials.write_text(json.dumps({"email": "docker-qa@example.invalid",
            "password": secrets.token_urlsafe(32), "display_name": "DEMO QA"}), encoding="utf-8")
    print("QA 配置已生成；凭据仅存本地忽略文件。")
