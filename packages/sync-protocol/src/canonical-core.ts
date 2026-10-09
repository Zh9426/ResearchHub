

const DECIMAL = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$/;
const INTEGER = /^(?:0|-?[1-9][0-9]*)$/;
export const MAX_NESTING = 64;

function scalar(value: string): string {
  for (let i = 0; i < value.length; i++) {
    const unit = value.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) throw new Error('invalid Unicode scalar');
    } else if (unit >= 0xdc00 && unit <= 0xdfff) throw new Error('invalid Unicode scalar');
  }
  return value;
}

export function canonicalBytes(value: unknown): Uint8Array {
  const visiting = new Set<object>();
  function encode(item: unknown, depth = 0): string {
    if (depth > MAX_NESTING) throw new Error('wire nesting exceeds 64 value edges');
    if (item === null) return 'null';
    if (typeof item === 'boolean') return item ? 'true' : 'false';
    if (typeof item === 'string') return JSON.stringify(scalar(item));
    if (typeof item === 'number' && Number.isSafeInteger(item) && !Object.is(item, -0)) return String(item);
    if (typeof item !== 'object' || item === null) throw new Error('unsupported wire value');
    if (visiting.has(item)) throw new Error('cyclic wire value');
    visiting.add(item);
    let encoded: string;
    if (Array.isArray(item)) {
      // Own keys must be exactly length and every dense index. Key count alone
      // lets an extra key compensate for a hole and silently disappear in map.
      const keys = Reflect.ownKeys(item);
      if (keys.length !== item.length + 1 || keys.some(key => typeof key !== 'string' || (key !== 'length' && (!/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= item.length)))) {
        throw new Error('sparse or extended array');
      }
      encoded = '[' + item.map(value => encode(value, depth + 1)).join(',') + ']';
    } else {
      const proto = Object.getPrototypeOf(item);
      if (proto !== Object.prototype && proto !== null) throw new Error('wire object must be plain');
      if (Object.getOwnPropertySymbols(item).length) throw new Error('symbol wire keys');
      const object = item as Record<string, unknown>;
      encoded = '{' + Object.keys(object).sort().map(key => JSON.stringify(scalar(key)) + ':' + encode(object[key], depth + 1)).join(',') + '}';
    }
    visiting.delete(item);
    return encoded;
  }
  return new TextEncoder().encode(encode(value));
}

export function strictLoads(raw: string | Uint8Array): unknown {
  const text = typeof raw === 'string' ? raw : new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw);
  let cursor = 0;
  const whitespace = () => { while (/[\x20\x09\x0a\x0d]/.test(text[cursor] ?? '')) cursor++; };
  const fail = (): never => { throw new Error('invalid strict JSON at ' + cursor); };
  function string(): string {
    const start = cursor++;
    while (cursor < text.length) {
      const character = text[cursor++];
      if (character === '"') return scalar(JSON.parse(text.slice(start, cursor)) as string);
      if (character === '\\') {
        if (cursor >= text.length) fail();
        cursor++;
      } else if (character.charCodeAt(0) < 32) fail();
    }
    return fail();
  }
  function parse(depth = 0): unknown {
    if (depth > MAX_NESTING) throw new Error('wire nesting exceeds 64 value edges');
    whitespace();
    if (text[cursor] === '"') return string();
    if (text[cursor] === '{') {
      cursor++;
      whitespace();
      const object: Record<string, unknown> = Object.create(null);
      if (text[cursor] === '}') { cursor++; return object; }
      while (true) {
        whitespace();
        if (text[cursor] !== '"') fail();
        const key = string();
        if (Object.hasOwn(object, key)) throw new Error('duplicate decoded object key');
        whitespace();
        if (text[cursor++] !== ':') fail();
        object[key] = parse(depth + 1);
        whitespace();
        const end = text[cursor++];
        if (end === '}') return object;
        if (end !== ',') fail();
      }
    }
    if (text[cursor] === '[') {
      cursor++;
      whitespace();
      const array: unknown[] = [];
      if (text[cursor] === ']') { cursor++; return array; }
      while (true) {
        array.push(parse(depth + 1));
        whitespace();
        const end = text[cursor++];
        if (end === ']') return array;
        if (end !== ',') fail();
      }
    }
    for (const [token, value] of [['null', null], ['true', true], ['false', false]] as const) {
      if (text.startsWith(token, cursor)) { cursor += token.length; return value; }
    }
    const token = text.slice(cursor).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/)?.[0];
    if (!token || token === '-0' || !INTEGER.test(token)) return fail();
    // BigInt checks before Number conversion, preventing unsafe rounding.
    if (token.length > 17 || BigInt(token) > 9007199254740991n || BigInt(token) < -9007199254740991n) throw new Error('unsafe native integer');
    cursor += token.length;
    return Number(token);
  }
  const value = parse();
  whitespace();
  if (cursor !== text.length) fail();
  canonicalBytes(value);
  return value;
}



export function validateDecimal(value: unknown): asserts value is string {
  if (typeof value !== 'string' || value.length > 1024 || !DECIMAL.test(value)) throw new Error('invalid decimal string');
  const exponent = value.split(/[eE]/)[1] ?? '0';
  const significant = exponent.replace(/^[+-]/, '').replace(/^0+/, '') || '0';
  if (significant.length > 6 || Math.abs(Number(exponent)) > 100000) throw new Error('decimal exponent exceeds limit');
}

export function validateInteger(value: unknown): asserts value is string {
  if (typeof value !== 'string' || !INTEGER.test(value)) throw new Error('invalid tagged integer');
}

function scientificKey(value: string): string {
  validateDecimal(value);
  const [coefficient, exponentString = '0'] = value.split(/[eE]/);
  let exponent = Number(exponentString) - (coefficient.split('.')[1]?.length ?? 0);
  const negative = coefficient.startsWith('-');
  const digits = coefficient.replace(/^-/, '').replace('.', '').replace(/^0+/, '');
  if (!digits) return '0';
  const stripped = digits.replace(/0+$/, '');
  exponent += digits.length - stripped.length;
  return `${negative ? '-' : ''}${stripped}e${exponent}`;
}

export function scientificEqual(a: string, b: string): boolean {
  return scientificKey(a) === scientificKey(b);
}
