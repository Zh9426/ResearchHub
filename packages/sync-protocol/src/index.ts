export { canonicalBytes, strictLoads, digest, scientificEqual } from './canonical.ts';
export { ProtocolError, SUPPORTED_VERSION_PAIRS, requireVersionPair, validateChange, validateTransaction, revision, transactionDigest } from './protocol.ts';
export type { ChangeSet, SyncTransaction, ActorContext } from './protocol.ts';
