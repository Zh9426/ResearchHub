import copy
import json
from pathlib import Path
import pytest
from researchhub.sync.secure.envelope import open_transaction, seal_transaction
from researchhub.sync.secure.nonce import NonceVault
from packages.secure_wire.envelope import validate_header, header_of
V = json.loads(Path('fixtures/sync/v2/envelope.TEST_ONLY.json').read_text(encoding='utf-8'))
KEY = bytes.fromhex(V['key_TEST_ONLY'])
SEED = bytes.fromhex(V['signing_seed_TEST_ONLY'])
PUB = bytes.fromhex(V['signing_public_key'])
ENV = V['cases'][0]['envelope']
BIND = {k: ENV[k] for k in ['opaque_project_id','sender_device_id','membership_epoch','key_epoch']}

def test_v2_open_fixed_and_reject_signed_version_mismatch():
    assert open_transaction(ENV, KEY, PUB, project_id=V['transaction']['project_id'], nonce_prefix=19, **BIND) == V['transaction']
    with pytest.raises(ValueError, match='TRANSACTION_BINDING_MISMATCH'):
        open_transaction(V['cases'][1]['envelope'], KEY, PUB, project_id=V['transaction']['project_id'], nonce_prefix=19, **BIND)

def test_v2_seal_derives_signed_versions(tmp_path):
    vault = NonceVault(tmp_path / 'nonce.sqlite')
    vault.register_new(KEY, 19)
    actual = seal_transaction(V['transaction'], KEY, SEED, vault, 19, message_id=ENV['message_id'], **BIND)
    assert actual == ENV

@pytest.mark.parametrize('kind', ['snapshot','artifact_manifest'])
def test_nontransaction_remains_v1(kind):
    header = header_of(ENV); header['record_type'] = kind
    with pytest.raises(ValueError): validate_header(header)

@pytest.mark.parametrize('pair', [(2,1),(1,2),(3,3),(True,True)])
def test_header_version_pairs(pair):
    header = header_of(ENV); header['protocol_version'],header['schema_version'] = pair
    with pytest.raises(ValueError): validate_header(header)
