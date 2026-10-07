"""Local STDIO entry point. Credentials remain outside the versioned package."""
import json
import os
import runpy
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    credential_file = root / 'storage' / 'runtime' / 'mcp-local.json'
    if not os.environ.get('RESEARCHHUB_API_TOKEN'):
        if not credential_file.is_file():
            raise SystemExit('Configure storage/runtime/mcp-local.json or RESEARCHHUB_API_TOKEN first.')
        settings = json.loads(credential_file.read_text(encoding='utf-8-sig'))
        os.environ['RESEARCHHUB_API_TOKEN'] = settings['token']
        os.environ.setdefault('RESEARCHHUB_API_URL', settings['api_url'])
    os.environ.setdefault('RESEARCHHUB_API_URL', 'http://localhost:3000')
    sys.path.insert(0, str(root))
    os.chdir(root)
    runpy.run_module('apps.mcp.server', run_name='__main__')


if __name__ == '__main__':
    main()
