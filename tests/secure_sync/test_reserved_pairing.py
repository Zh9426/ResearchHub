"""A committed coordinator reservation never regenerates a challenge or grant."""
from uuid import uuid4
import pytest
from packages.secure_wire.canonical import digest
from tests.secure_sync.test_lifecycle import api, setup_project


def reserved(p, store, owner, recipient, old, session, **changes):
    args=dict(session_id=session, project=old['opaque_project_id'],
              expected_manifest_digest=digest(old), issued_at=100, now=101)
    args.update(changes)
    return p.create_or_load_reserved_challenge(store, owner, recipient, **args)


def test_reserved_exact_bytes_survive_use_and_expiry(tmp_path):
    k, owner, b, _, old, store=setup_project(tmp_path)
    p=api('pairing'); sid=str(uuid4()); recipient=b.member('writer',1)
    first=reserved(p,store,owner,recipient,old,sid)
    assert reserved(p,store,owner,recipient,old,sid)==first
    proof=p.answer_challenge(first,old,b,confirmation=p.confirmation(first),now=102)
    receipt=p.consume(store,owner,first,proof,bytes(32),now=103)
    assert reserved(p,k.TrustedStore(store.path),owner,recipient,old,sid,now=500)==first
    assert p.retry_receipt(store,first,b.device_id)==receipt
    with store.transaction() as db:
        assert db.execute('SELECT attempts,used FROM challenges WHERE session=?',(sid,)).fetchone()==(1,1)


@pytest.mark.parametrize('change', ['project','session_id','expected_manifest_digest','issued_at','recipient'])
def test_reserved_scope_cannot_be_replaced(tmp_path, change):
    _,owner,b,_,old,store=setup_project(tmp_path); p=api('pairing'); sid=str(uuid4())
    recipient=b.member('writer',1); reserved(p,store,owner,recipient,old,sid)
    changes={change: str(uuid4()) if change in ('project','session_id') else 'a'*64 if change=='expected_manifest_digest' else 101}
    if change=='recipient': recipient={**recipient,'role':'reader'}; changes={}
    if change=='session_id':
        # Another reservation is not an alias for the existing exact session.
        assert reserved(p,store,owner,recipient,old,sid,**changes)['session_id']!=sid
    else:
        with pytest.raises(ValueError):reserved(p,store,owner,recipient,old,sid,**changes)


def test_uncreated_expired_reservation_stays_uncreated(tmp_path):
    _,owner,b,_,old,store=setup_project(tmp_path); p=api('pairing')
    with pytest.raises(ValueError,match='PAIRING_EXPIRED'):
        reserved(p,store,owner,b.member('writer',1),old,str(uuid4()),now=400)
    with store.transaction() as db: assert db.execute('SELECT count(*) FROM challenges').fetchone()[0]==0
