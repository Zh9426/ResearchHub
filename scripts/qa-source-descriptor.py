"""Read one bounded, owned 3A descriptor as the isolated browser OS user.

Output is private input for the PC CLI, never a public CI artifact.
"""
import json
import os
from pathlib import Path
import stat
import sys


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_SOURCE_KEY')
        result[key] = value
    return result


def read_descriptor(path, home, uid):
    path, home = Path(path), Path(home).resolve()
    if path.name != 'source-project.json' or path.is_symlink() or not path.resolve().is_relative_to(home):
        raise ValueError('SOURCE_PATH_REJECTED')
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_size > 1024 * 1024:
            raise ValueError('SOURCE_FILE_REJECTED')
        raw = source.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('SOURCE_FILE_REJECTED')
    value = json.loads(raw, object_pairs_hook=unique_pairs)
    if not isinstance(value, dict) or set(value) != {'format', 'project'} or value['format'] != 'RESEARCHHUB_3A_SOURCE_PROJECT_V1':
        raise ValueError('SOURCE_FORMAT_REJECTED')
    if not isinstance(value['project'], dict) or set(value['project']) != {
        'id', 'route_alias', 'title', 'scope', 'module_id', 'module_version',
        'module_snapshot', 'module_hash', 'local_format_version'}:
        raise ValueError('SOURCE_FORMAT_REJECTED')
    return raw


if __name__ == '__main__':
    if sys.platform != 'linux' or os.getuid() == 0 or len(sys.argv) != 2:
        raise RuntimeError('ISOLATED_NONROOT_LINUX_USER_REQUIRED')
    sys.stdout.buffer.write(read_descriptor(sys.argv[1], Path.home(), os.getuid()))
