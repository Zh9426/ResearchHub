import { digest } from '../../sync-protocol/src/browser.ts';
import { verifyChallenge, preimage, type PublicObject } from './membership-core.ts';
import { unwrapKey, sign, type DeviceKeys } from './crypto-web.ts';
import { b64decode, b64encode, hexEncode } from './binary.ts';
export const confirmation = (c: PublicObject) => ({ fingerprint: c.recipient.fingerprint, opaque_project_id: c.opaque_project_id, role: c.recipient.role, sas: c.sas });
export async function answerChallenge(c: PublicObject, pinned: PublicObject, device: DeviceKeys, options: {
    confirmation: PublicObject;
    now: number;
}): Promise<PublicObject> {
    await verifyChallenge(c, pinned, options.now);
    if (await digest(options.confirmation) !== await digest(confirmation(c)))
        throw Error('PAIRING_CONFIRMATION_MISMATCH');
    const r = c.recipient;
    if (r.device_id !== device.deviceId || r.signing_public_key !== device.signingPublic || r.recipient_public_key !== device.recipientPublic)
        throw Error('RECIPIENT_MISMATCH');
    const response = await unwrapKey(device.recipient, b64decode(c.wrapped_challenge, 80), { opaque_project_id: pinned.opaque_project_id, recipient_device_id: r.device_id, key_epoch: pinned.key_epoch, membership_epoch: pinned.membership_epoch, session_id: c.session_id, recipient_signing_public_key: r.signing_public_key, recipient_public_key: r.recipient_public_key });
    const proof: PublicObject = { challenge_digest: await digest(c), challenge_response: hexEncode(response), confirmation: options.confirmation };
    proof.signature = b64encode(await sign(device.signing.privateKey, preimage('PairingProof', proof)));
    return proof;
}
