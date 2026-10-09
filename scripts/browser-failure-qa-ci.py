"""One independent disposable Linux VM per fixed fault case."""
import argparse
import importlib.util
from pathlib import Path
from browser_failure_control import CASE_ACTIONS

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=tuple(CASE_ACTIONS))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('browser_network_matrix_harness', Path(__file__).with_name('browser-network-qa-ci.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    raise SystemExit(module.main('failure-' + args.case))
