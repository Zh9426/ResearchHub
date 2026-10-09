/** Platform-neutral byte encodings. No secret export helpers. */
export const bytes = (v: Uint8Array): ArrayBuffer => Uint8Array.from(v).buffer;
export const text = (v: string) => new TextEncoder().encode(v);
export const hexEncode = (v: Uint8Array) => Array.from(v, b => b.toString(16).padStart(2, '0')).join('');
export function hexDecode(v: string): Uint8Array {
    if (!/^(?:[0-9a-f]{2})*$/.test(v))
        throw Error('INVALID_HEX');
    return Uint8Array.from(v.match(/../g) ?? [], x => parseInt(x, 16));
}
export function concat(...parts: Uint8Array[]): Uint8Array {
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let i = 0;
    for (const p of parts) {
        out.set(p, i);
        i += p.length;
    }
    return out;
}
export const equal = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((v, i) => v === b[i]);
export const b64encode = (v: Uint8Array) => btoa(Array.from(v, b => String.fromCharCode(b)).join('')).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
export function b64decode(value: unknown, size?: number): Uint8Array {
    if (typeof value !== 'string' || !/^[A-Za-z0-9_-]*$/.test(value))
        throw Error('INVALID_ENVELOPE');
    let raw: Uint8Array;
    try {
        raw = Uint8Array.from(atob(value.replaceAll('-', '+').replaceAll('_', '/')), x => x.charCodeAt(0));
    }
    catch {
        throw Error('INVALID_ENVELOPE');
    }
    if (b64encode(raw) !== value || (size !== undefined && raw.length !== size))
        throw Error('INVALID_ENVELOPE');
    return raw;
}
export function nonceParts(nonce: Uint8Array) {
    if (nonce.length !== 12)
        throw Error('INVALID_KEY_OR_NONCE');
    const v = new DataView(nonce.buffer, nonce.byteOffset, nonce.byteLength);
    return { prefix: v.getUint32(0), counter: v.getBigUint64(4) };
}
