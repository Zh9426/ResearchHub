"""Export the validated API input contract for UI and external clients."""

import json
from pathlib import Path

from .modules import Manifest
from .schemas import SCHEMAS


def main():
    target = Path(__file__).resolve().parents[3] / "packages" / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    for name, schema in {**SCHEMAS, "module-manifest": Manifest}.items():
        (target / f"{name}.schema.json").write_text(
            json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
