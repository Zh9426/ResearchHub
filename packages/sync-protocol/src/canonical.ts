import { createHash } from 'node:crypto';
import { canonicalBytes } from './canonical-core.ts';
export * from './canonical-core.ts';
export function digest(value: unknown): string {
  return createHash('sha256').update(canonicalBytes(value)).digest('hex');
}
