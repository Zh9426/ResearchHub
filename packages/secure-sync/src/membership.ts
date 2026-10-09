/** Node compatibility facade. Async verification rules are shared with Chromium. */
import {digest} from '../../sync-protocol/src/canonical.ts';
import {validateMemberShape,validateManifestShape,hex,type PublicObject} from './membership-core.ts';
export {ZERO,fields,integer,hex,uuid,preimage,verifySigned,memberOf,verifyBootstrap,verifyTransition,validateContext,verifyGrant,verifyChallenge,verifyActiveEnvelope,verifyHistoricalEnvelope} from './membership-core.ts';
export type {PublicObject} from './membership-core.ts';
export function fingerprint(signing:string,recipient:string):string {hex(signing,32);hex(recipient,32);return digest({signing_public_key:signing,recipient_public_key:recipient});}
export function validateMember(m:PublicObject):void {validateMemberShape(m);if(m.fingerprint!==fingerprint(m.signing_public_key,m.recipient_public_key))throw Error('FINGERPRINT_MISMATCH');}
export function validateManifest(m:PublicObject):void {validateManifestShape(m);m.members.forEach(validateMember);}
export function challengeSas(c:PublicObject):string {return digest(Object.fromEntries(Object.entries(c).filter(([k])=>!['signature','sas'].includes(k)))).slice(0,12);}
