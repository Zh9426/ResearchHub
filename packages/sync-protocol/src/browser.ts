/** Browser wire boundary: exact shared core, asynchronous WebCrypto hashing. */
import { canonicalBytes } from './canonical-core.ts';
import { validateChange, validateTransaction } from './protocol-core.ts';
export * from './canonical-core.ts';
export * from './protocol-core.ts';
export async function digest(value: unknown): Promise<string> {
  const bytes = Uint8Array.from(canonicalBytes(value));
  const result = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(result), byte => byte.toString(16).padStart(2, '0')).join('');
}
export async function revision(change: unknown): Promise<string> { return digest(validateChange(change)); }
export async function transactionDigest(tx: unknown): Promise<string> { return digest(validateTransaction(tx)); }
