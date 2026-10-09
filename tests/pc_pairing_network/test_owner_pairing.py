"""REAL_HTTPS happy path; keeps existing Relay resources and other project rows."""
import os
import time
from pathlib import Path
from uuid import uuid4
import pytest
from researchhub.sync.pc_identity import setup_node, current_binding
from researchhub.sync.secure import pairing
from researchhub.sync.secure.keys import Device, open_grant


def test_owner_pairing_real_strict_tls_and_current_chain(engine):
    assert os.environ.get('HUB_RELAY_QA')=='1', 'Explicit real HTTPS QA opt-in required'
    from researchhub.sync.pc_pairing import OwnerPairing, make_transport, pin_node_bootstrap
    node=setup_node(engine,Path('storage/runtime/browser-sync-qa/pc/b2a-network')/str(uuid4()))
    pin_node_bootstrap(node)
    transport=make_transport(engine,node)
    try:
        owner=OwnerPairing(engine,node,transport);b=Device.generate();now=int(time.time())
        started=owner.start(b.member('writer',1),now=now)
        proof=pairing.answer_challenge(started['challenge'],node.binding['trust']['manifest_chain'][-1],
            b,confirmation=started['confirmation'],now=now)
        result=owner.confirm(started['session_id'],proof,now=now)
        assert result['stage']=='COMPLETE'
        receipt=result['pairing_receipt']
        assert bool(open_grant(receipt['grant'],receipt['manifest'],b)==node.project_key)
        assert transport.request('GET','/v1/membership')==receipt['manifest']
        binding,_=current_binding(engine,node)
        assert binding['principal_map']==result['signed_binding']['binding']['principal_map']
        assert owner.resume(started['session_id'],now=now+400)==result
    finally:transport.close()
