"""The owner bridge must not follow links or accept unrelated private files."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('source_bridge', Path(__file__).resolve().parents[1] / 'scripts/qa-source-descriptor.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def source(tmp_path):
    value = {'format': 'RESEARCHHUB_3A_SOURCE_PROJECT_V1', 'project': {
        'id': 'synthetic', 'route_alias': 'hdsp', 'title': 'SYNTHETIC',
        'scope': 'SYNTHETIC', 'module_id': 'hdsp', 'module_version': '1',
        'module_snapshot': {}, 'module_hash': 'a' * 64, 'local_format_version': 1}}
    path = tmp_path / 'source-project.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def test_bridge_preserves_bytes_and_rejects_wrong_owner_or_location(tmp_path):
    path = source(tmp_path)
    uid = path.stat().st_uid
    assert bridge.read_descriptor(path, tmp_path, uid) == path.read_bytes()
    with pytest.raises(ValueError, match='SOURCE_FILE_REJECTED'):
        bridge.read_descriptor(path, tmp_path, uid + 1)
    with pytest.raises(ValueError, match='SOURCE_PATH_REJECTED'):
        bridge.read_descriptor(path, tmp_path / 'other', uid)


def test_bridge_rejects_link_before_reading(tmp_path, monkeypatch):
    path = source(tmp_path)
    monkeypatch.setattr(Path, 'is_symlink', lambda _: True)
    with pytest.raises(ValueError, match='SOURCE_PATH_REJECTED'):
        bridge.read_descriptor(path, tmp_path, path.stat().st_uid)


@pytest.mark.parametrize('raw', [
    '{"format":"RESEARCHHUB_3A_SOURCE_PROJECT_V1","format":"duplicate","project":{}}',
    '{"format":"RESEARCHHUB_3A_SOURCE_PROJECT_V1","project":{},"private_key":"SYNTHETIC"}',
    'x' * (1024 * 1024 + 1),
], ids=['duplicate-key', 'unrelated-field', 'oversized'])
def test_bridge_rejects_ambiguous_unrelated_and_oversized_files(tmp_path, raw):
    path = source(tmp_path)
    path.write_text(raw, encoding='utf-8')
    with pytest.raises(ValueError):
        bridge.read_descriptor(path, tmp_path, path.stat().st_uid)
