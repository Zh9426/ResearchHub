import { digest } from './canonical.ts';
import { validateChange, validateTransaction } from './protocol-core.ts';
export * from './protocol-core.ts';
export function revision(change: unknown): string { return digest(validateChange(change)); }
export function transactionDigest(tx: unknown): string { return digest(validateTransaction(tx)); }
