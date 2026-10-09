"""Fixed, non-secret failure-matrix control protocol. No user-selected resources."""
import json
import os
from pathlib import Path
import stat

CASE_ACTIONS = {
    'reopen': ('VERIFY_DURABLE_COUNTS', 'VERIFY_DURABLE_COUNTS', 'CASE_FINISH'),
    'pc-offline': ('PC_STOP', 'PC_START', 'VERIFY_DURABLE_COUNTS', 'VERIFY_DURABLE_COUNTS', 'CASE_FINISH'),
    'independent-echo': ('VERIFY_DURABLE_COUNTS', 'VERIFY_DURABLE_COUNTS', 'CASE_FINISH'),
    'ack-loss': ('ACKLOSS_ARM', 'ACKLOSS_WAIT_COMMIT_AND_KILL', 'RELAY_START', 'VERIFY_DURABLE_COUNTS', 'VERIFY_DURABLE_COUNTS', 'CASE_FINISH'),
    'revoked-write': ('OWNER_REVOKE', 'VERIFY_DURABLE_COUNTS', 'VERIFY_DURABLE_COUNTS', 'CASE_FINISH'),
    'historical-bootstrap': ('VERIFY_DURABLE_COUNTS', 'VERIFY_DURABLE_COUNTS', 'CASE_FINISH'),
    'privacy': ('PRIVACY_AUDIT', 'CASE_FINISH'),
}

CONTROL_ERRORS = frozenset('ACKLOSS_EMPTY_BASELINE_REQUIRED ACKLOSS_BARRIER_NOT_REACHED ACKLOSS_DURABLE_COMMIT_REQUIRED ACKLOSS_KILL_WINDOW_EXCEEDED ACKLOSS_ORIGINAL_MESSAGE_CHANGED DURABLE_EXPECTED_COUNTS_MISMATCH DURABLE_COUNTS_OR_IDENTITIES_CHANGED ONE_PAIRED_WRITER_REQUIRED OWNER_REVOKE_RECEIPT_MISMATCH PRIVACY_POSITIVE_CONTROL_NOT_DETECTED PRIVACY_CONTROL_ID_COLLISION PRIVACY_CONTROL_CHANGED PRIVACY_CONTROL_CLEANUP_FAILED MATRIX_PC_OWNER_MISMATCH MATRIX_PC_STOP_FAILED MATRIX_PC_STILL_RUNNING CONTROL_PROTOCOL_REJECTED CONTROL_FILE_REJECTED CONTROL_DIRECTORY_REJECTED'.split())


def public_control_error(error):
    kind = type(error).__name__
    return {'errorClass': kind if kind in {'ValueError', 'RuntimeError', 'OSError', 'TimeoutExpired', 'ExceptionGroup'} else 'UNKNOWN',
            'code': str(error) if str(error) in CONTROL_ERRORS else 'UNCLASSIFIED'}


def strict_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('CONTROL_PROTOCOL_REJECTED')
        value[key] = item
    return value


class Protocol:
    def __init__(self, case):
        if not isinstance(case, str) or case not in CASE_ACTIONS:
            raise ValueError('CONTROL_PROTOCOL_REJECTED')
        self.case, self.step = case, 0

    @property
    def finished(self):
        return self.step == len(CASE_ACTIONS[self.case])

    def accept(self, raw):
        try:
            if not isinstance(raw, bytes) or len(raw) > 1024:
                raise ValueError()
            value = json.loads(raw, object_pairs_hook=strict_pairs)
            if (not isinstance(value, dict) or set(value) != {'version', 'case', 'step', 'action'}
                    or type(value['version']) is not int or value['version'] != 1
                    or value['case'] != self.case or type(value['step']) is not int
                    or value['step'] != self.step + 1 or self.finished
                    or value['action'] != CASE_ACTIONS[self.case][self.step]):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise ValueError('CONTROL_PROTOCOL_REJECTED') from None
        self.step += 1
        return value['action']


def read_owned_file(path, uid):
    """Open without following links and compare inode before and after open."""
    path = Path(path)
    info = path.lstat()
    def safe(value):
        return (stat.S_ISREG(value.st_mode) and value.st_uid == uid
                and value.st_nlink == 1 and value.st_size <= 1024)
    if not safe(info):
        raise ValueError('CONTROL_FILE_REJECTED')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    try:
        opened = os.fstat(descriptor)
        if not safe(opened) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('CONTROL_FILE_REJECTED')
        raw = os.read(descriptor, 1025)
        final = os.fstat(descriptor)
        if len(raw) != opened.st_size or len(raw) > 1024 or final.st_size != opened.st_size:
            raise ValueError('CONTROL_FILE_REJECTED')
        return raw
    finally:
        os.close(descriptor)

class RealActions:
    """Runner-owned resources only. Browser supplies no project, path, PID or SQL."""
    def __init__(self, root, node_path, stop_pc, start_pc, evidence):
        import importlib.util
        import sys
        self.root, self.node_path = Path(root), Path(node_path)
        sys.path[:0] = [str(self.root / 'apps/api'), str(self.root / 'apps/relay'), str(self.root)]
        spec = importlib.util.spec_from_file_location('matrix_relay_lifecycle', self.root / 'scripts/secure-relay-qa.py')
        self.q = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.q)
        self.config = self.q.config()
        self.state = json.loads(self.q.STATE.read_text())
        self.q.guard_state(self.state, self.config)
        from researchhub_relay.qa import connect
        from researchhub.sync.secure.transport_pg import client_engine
        self.relay_engine = connect(self.q.url(self.config), profile='host')
        self.pc_engine = client_engine()
        self.stop_pc, self.start_pc, self.evidence = stop_pc, start_pc, evidence
        self.node = None
        self.prior = None
        self.lost = None

    def close(self):
        self.relay_engine.dispose(); self.pc_engine.dispose()

    def owned_node(self):
        if self.node is None:
            from researchhub.sync.pc_identity import setup_node
            self.node = setup_node(self.pc_engine, self.node_path)
        return self.node

    def relay(self, *args):
        self.q.guard_state(self.state, self.config)
        return self.q.docker(*args)

    def relay_rows(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from researchhub_relay.models import Message, Project
        node = self.owned_node()
        with Session(self.relay_engine) as db:
            project = node.binding['opaque_project_id']
            rows = db.scalars(select(Message).where(Message.project == project).order_by(Message.sequence)).all()
            return db.get(Project, project).sequence, [
                (r.id, bytes(r.body), r.digest, r.nonce, r.sequence, bytes(r.receipt)) for r in rows]

    def counts(self):
        import hashlib
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from researchhub.sync.models import SyncTransaction, ObjectRevision, Audit, Inbox
        from packages.secure_wire.canonical import canonical_bytes
        from researchhub.sync.secure.transport_pg import guard
        self.q.guard_state(self.state, self.config); guard(self.pc_engine)
        sequence, messages = self.relay_rows()
        node = self.owned_node()
        result = {'relay_sequence': sequence, 'relay_messages': len(messages),
                  'relay_digest': hashlib.sha256(repr(messages).encode()).hexdigest()}
        with Session(self.pc_engine) as db:
            for model in (SyncTransaction, ObjectRevision, Audit, Inbox):
                rows = db.execute(select(model.__table__).where(model.project_id == node.binding['semantic_project_id'])).mappings().all()
                values = sorted((dict(row) for row in rows), key=lambda r: json.dumps(r, sort_keys=True))
                result[model.__name__] = len(values)
                result[model.__name__ + '_digest'] = hashlib.sha256(canonical_bytes(values)).hexdigest()
        return result

    def perform(self, action):
        import time
        relay = self.state['containers'][self.q.RELAY]
        if action == 'PC_STOP':
            self.stop_pc()
            self.q.guard_state(self.state, self.config)
            self.q.wait_tls(self.state)
            self.evidence['pc_logical_offline_relay_live'] = True
        elif action == 'PC_START':
            self.start_pc()
        elif action == 'ACKLOSS_ARM':
            sequence, rows = self.relay_rows()
            if sequence != 0 or rows:
                raise RuntimeError('ACKLOSS_EMPTY_BASELINE_REQUIRED')
            self.relay('exec', relay, 'python', '-c',
                "from pathlib import Path; p=Path('/fault'); [(p/n).unlink(missing_ok=True) for n in ('arm','reached','release')]; (p/'arm').write_text('after_commit')")
        elif action == 'ACKLOSS_WAIT_COMMIT_AND_KILL':
            started = time.monotonic(); deadline = started + 10
            while True:
                reached = self.q.docker('exec', relay, 'python', '-c',
                    "from pathlib import Path; p=Path('/fault/reached'); print(p.read_text() if p.exists() else 'waiting')").strip()
                if reached == b'after_commit':
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('ACKLOSS_BARRIER_NOT_REACHED')
                time.sleep(.05)
            sequence, rows = self.relay_rows()
            if sequence != 1 or len(rows) != 1:
                raise RuntimeError('ACKLOSS_DURABLE_COMMIT_REQUIRED')
            self.lost = rows[0]
            committed = time.monotonic()
            self.relay('kill', '--signal', 'KILL', relay)
            killed = time.monotonic()
            if killed - started >= 15:
                raise RuntimeError('ACKLOSS_KILL_WINDOW_EXCEEDED')
            self.evidence['ackloss'] = {'barrier': 'after_commit', 'durable_messages': 1,
                'commit_observed_before_kill': committed <= killed,
                'kill_observed_within_fetch_deadline': True}
        elif action == 'RELAY_START':
            self.relay('start', relay); self.q.wait_tls(self.state)
        elif action == 'VERIFY_DURABLE_COUNTS':
            current = self.counts()
            self.evidence.setdefault('durable_checks', []).append(current)
            expected = {'historical-bootstrap': 1, 'revoked-write': 0, 'independent-echo': 6}.get(self.evidence['case'], 5)
            if any(current[key] != expected for key in ('relay_sequence', 'relay_messages', 'SyncTransaction', 'ObjectRevision', 'Audit', 'Inbox')):
                raise RuntimeError('DURABLE_EXPECTED_COUNTS_MISMATCH')
            if self.lost is not None:
                rows = self.relay_rows()[1]
                if [r for r in rows if r[0] == self.lost[0]] != [self.lost]:
                    raise RuntimeError('ACKLOSS_ORIGINAL_MESSAGE_CHANGED')
                self.evidence['ackloss']['original_envelope_nonce_receipt_sequence_unchanged'] = True
            if self.prior is not None and current != self.prior:
                raise RuntimeError('DURABLE_COUNTS_OR_IDENTITIES_CHANGED')
            self.prior = current
        elif action == 'OWNER_REVOKE':
            from researchhub.sync.secure.keys import transition, TrustedStore
            from researchhub.sync.secure.transport_pg import advance_history
            from researchhub.sync.pc_identity import current_binding
            from researchhub.sync.pc_pairing import make_transport
            from packages.secure_wire.canonical import digest
            node = self.owned_node()
            binding, _ = current_binding(self.pc_engine, node)
            previous = binding['trust']['manifest_chain'][-1]
            writers = [m for m in previous['members'] if m['role'] == 'writer' and m['status'] == 'ACTIVE']
            if len(writers) != 1:
                raise RuntimeError('ONE_PAIRED_WRITER_REQUIRED')
            candidate = transition(previous, node.owner, revoke=writers[0]['device_id'])
            transport = make_transport(self.pc_engine, node)
            try:
                result = transport.request('POST', '/v1/membership', {'manifest': candidate})
            finally:
                transport.close()
            if result['manifest_digest'] != digest(candidate):
                raise RuntimeError('OWNER_REVOKE_RECEIPT_MISMATCH')
            advance_history(self.pc_engine, binding['opaque_project_id'], candidate)
            TrustedStore(node.runtime / 'trust.sqlite').accept(candidate)
            self.evidence['owner_revoke'] = {'published': True, 'membership_epoch': candidate['membership_epoch'], 'key_epoch': candidate['key_epoch']}
        elif action == 'PRIVACY_AUDIT':
            self.privacy()
        elif action != 'CASE_FINISH':
            raise ValueError('CONTROL_PROTOCOL_REJECTED')

    def privacy(self):
        import importlib.util
        from uuid import uuid4
        from sqlalchemy.orm import Session
        from researchhub_relay.models import PublicObject
        node = self.owned_node()
        spec = importlib.util.spec_from_file_location('matrix_privacy', self.root / 'tests/secure_relay/privacy.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        network = {'lifecycle': self.q, 'state': self.state, 'config': self.config, 'engine': self.relay_engine,
                   'audit_context': {'trial': 'browser-privacy-matrix', 'cohort': 'native-browser', 'invocation': self.state['run']}}
        inventory = [node.owner.signing_seed, node.owner.recipient_seed, node.project_key]
        canaries = [s.encode() for s in ('SYNTHETIC_MATRIX_RUN_7c91', 'SYNTHETIC_MATRIX_OBSERVATION_9ea2',
            'SYNTHETIC_MATRIX_NOTE_a05d', 'SYNTHETIC_MATRIX_STAR_39ef')]
        module.audit(network, inventory, canaries)
        # A separate newly allocated public control row, never a business table.
        identity = (node.binding['opaque_project_id'], 'privacy_control', str(uuid4()))
        sentinel = b'SYNTHETIC_MATRIX_POSITIVE_CONTROL_f480a2'
        detected = False
        inserted = False
        errors = []
        try:
            with Session(self.relay_engine) as db, db.begin():
                if db.get(PublicObject, identity) is not None:
                    raise RuntimeError('PRIVACY_CONTROL_ID_COLLISION')
                inserted = True
                db.add(PublicObject(project=identity[0], kind=identity[1], id=identity[2], body=sentinel))
            try:
                module.audit(network, inventory, [*canaries, sentinel])
            except RuntimeError as error:
                if str(error) != 'PRIVACY_NONZERO_HITS values suppressed':
                    raise
                detected = True
            if not detected:
                raise RuntimeError('PRIVACY_POSITIVE_CONTROL_NOT_DETECTED')
        except Exception as error:
            errors.append(error)
        try:
            if inserted:
                with Session(self.relay_engine) as db, db.begin():
                    row = db.get(PublicObject, identity)
                    if row is not None:
                        if bytes(row.body) != sentinel:
                            raise RuntimeError('PRIVACY_CONTROL_CHANGED')
                        db.delete(row)
                with Session(self.relay_engine) as db:
                    if db.get(PublicObject, identity) is not None:
                        raise RuntimeError('PRIVACY_CONTROL_CLEANUP_FAILED')
        except Exception as error:
            errors.append(error)
        if errors:
            raise ExceptionGroup('PRIVACY_CONTROL_OR_CLEANUP_FAILED', errors)
        module.audit(network, inventory, [*canaries, sentinel])
        self.evidence['privacy'] = {'positive_control_detected': detected, 'exact_control_removed': True,
            'final_hits': 0, 'known_pc_private_material_count': len(inventory),
            'browser_nonextractable_raw_key_scan': 'NOT_POSSIBLE',
            'sources': ['actual_pg_dump', 'driver_decoded_all_bytea', 'owned_files', 'owned_logs']}

class Controller:
    def __init__(self, case, directory, browser_uid, actions, evidence):
        self.protocol = Protocol(case)
        evidence['case'] = case
        self.directory = Path(directory)
        self.browser_uid, self.actions, self.evidence = browser_uid, actions, evidence
        self.directory_identity = self.directory.stat()
        if (self.directory.is_symlink() or self.directory_identity.st_uid != os.getuid()
                or stat.S_IMODE(self.directory_identity.st_mode) != 0o1733):
            raise ValueError('CONTROL_DIRECTORY_REJECTED')

    def poll(self):
        now = self.directory.lstat()
        if (not stat.S_ISDIR(now.st_mode) or now.st_uid != os.getuid()
                or (now.st_dev, now.st_ino) != (self.directory_identity.st_dev, self.directory_identity.st_ino)
                or stat.S_IMODE(now.st_mode) != 0o1733):
            raise ValueError('CONTROL_DIRECTORY_REJECTED')
        if self.protocol.finished:
            return
        step = self.protocol.step + 1
        path = self.directory / f'{step:03d}.request.json'
        try:
            raw = read_owned_file(path, self.browser_uid)
        except FileNotFoundError:
            return
        action = self.protocol.accept(raw)
        try:
            self.actions.perform(action)
        except Exception as primary:
            self.evidence.setdefault('control', []).append({'step': step, 'action': action, 'status': 'FAILED'})
            self.evidence['control_failure'] = public_control_error(primary)
            try:
                self.respond(step, 'FAILED')
            except Exception as response_error:
                raise ExceptionGroup('CONTROL_AND_RESPONSE_FAILED', [primary, response_error])
            raise
        self.respond(step, 'PASS')
        self.evidence.setdefault('control', []).append({'step': step, 'action': action, 'status': 'PASS'})

    def respond(self, step, status):
        raw = json.dumps({'version': 1, 'case': self.protocol.case, 'step': step, 'status': status}).encode()
        path = self.directory / f'{step:03d}.response.json'
        temporary = self.directory / f'{step:03d}.response.tmp'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.fchmod(descriptor, 0o644)
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, path)  # Exclusive publication: never overwrite browser-created paths.
        temporary.unlink()


def run_controlled(args, *, cwd, env, log, timeout, controller):
    """One child, bounded polling; no retry. Preserve action failures and reap child."""
    import subprocess
    import time
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    errors = []
    code = None
    try:
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(args, timeout)
            controller.poll()
            time.sleep(.05)
        if process.returncode == 0 and not controller.protocol.finished:
            raise RuntimeError('CONTROL_CASE_NOT_FINISHED')
        code = process.returncode
    except Exception as error:
        errors.append(error)
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
    except Exception as error:
        errors.append(error)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise ExceptionGroup('CONTROLLED_RUN_AND_CLEANUP_FAILED', errors)
    return code
