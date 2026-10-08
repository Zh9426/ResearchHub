/** TEST ONLY trusted nonce vault. Never stored on Relay. */
import { DatabaseSync } from 'node:sqlite';
import { existsSync, readFileSync, openSync, writeSync, fsyncSync, closeSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { canonicalBytes, strictLoads } from '../../sync-protocol/src/canonical.ts';
type Row = {
    identity: string;
    counter: number;
};
export class NonceVault {
    path: string;
    witnessPath: string;
    anchorPath: string;
    constructor(path: string) { this.path = path; this.witnessPath = path + '.witness'; this.anchorPath = path + '.anchor'; }
    identity(key: Uint8Array, prefix: number): string {
        if (key.length !== 32 || !Number.isInteger(prefix) || prefix < 0 || prefix > 4294967295)
            throw new Error('NONCE_STATE_INVALID');
        return createHash('sha256').update(key).digest('hex') + ':' + prefix;
    }
    initialize(): void {
        const present = [this.path, this.witnessPath, this.anchorPath].map(existsSync);
        if (present.some(Boolean)) {
            if (!present.every(Boolean))
                throw new Error('NONCE_STATE_INVALID');
            return;
        }
        mkdirSync(dirname(this.path), { recursive: true });
        let fd = openSync(this.anchorPath, 'wx', 0o600);
        try {
            writeSync(fd, 'RH-NONCE-1\n');
            fsyncSync(fd);
        }
        finally {
            closeSync(fd);
        }
        const db = new DatabaseSync(this.path);
        try {
            db.exec('PRAGMA synchronous=FULL; CREATE TABLE nonces (identity TEXT PRIMARY KEY, counter INTEGER NOT NULL)');
        }
        finally {
            db.close();
        }
        fd = openSync(this.witnessPath, 'wx', 0o600);
        try {
            fsyncSync(fd);
        }
        finally {
            closeSync(fd);
        }
    }
    connect(): DatabaseSync {
        if (![this.path, this.witnessPath, this.anchorPath].every(existsSync))
            throw new Error('NONCE_STATE_INVALID');
        const db = new DatabaseSync(this.path);
        try {
            db.exec('PRAGMA busy_timeout=30000; PRAGMA synchronous=FULL; BEGIN IMMEDIATE');
            return db;
        }
        catch {
            db.close();
            throw new Error('NONCE_STATE_INVALID');
        }
    }
    validate(db: DatabaseSync): Map<string, number> {
        if (readFileSync(this.anchorPath).toString() !== 'RH-NONCE-1\n')
            throw new Error('NONCE_STATE_INVALID');
        const raw = readFileSync(this.witnessPath), latest = new Map<string, number>();
        if (raw.length && raw.at(-1) !== 10)
            throw new Error('NONCE_STATE_INVALID');
        for (const line of raw.toString('utf8').split('\n').slice(0, -1)) {
            const value = strictLoads(line) as Row;
            if (!value || Object.keys(value).sort().join() !== 'counter,identity' || Buffer.from(canonicalBytes(value)).toString() !== line || !(/^[0-9a-f]{64}:(0|[1-9][0-9]*)$/).test(value.identity) || Number(value.identity.split(':')[1]) > 4294967295 || !Number.isSafeInteger(value.counter) || value.counter < 0 || value.counter !== (latest.get(value.identity) ?? -1) + 1)
                throw new Error('NONCE_STATE_INVALID');
            latest.set(value.identity, value.counter);
        }
        const rows = db.prepare('SELECT identity,counter FROM nonces').all() as Row[];
        if (rows.length !== latest.size || rows.some(row => latest.get(row.identity) !== row.counter))
            throw new Error('NONCE_STATE_INVALID');
        return latest;
    }
    append(identity: string, counter: number): void {
        const fd = openSync(this.witnessPath, 'a');
        try {
            const data = Buffer.concat([Buffer.from(canonicalBytes({ identity, counter })), Buffer.from('\n')]);
            if (writeSync(fd, data) !== data.length)
                throw new Error('NONCE_STATE_INVALID');
            fsyncSync(fd);
        }
        finally {
            closeSync(fd);
        }
    }
    registerNew(key: Uint8Array, prefix: number): void {
        const identity = this.identity(key, prefix);
        this.initialize();
        const db = this.connect();
        try {
            const rows = this.validate(db);
            if (rows.has(identity))
                throw new Error('NONCE_ALREADY_REGISTERED');
            db.prepare('INSERT INTO nonces VALUES (?,0)').run(identity);
            this.append(identity, 0);
            db.exec('COMMIT');
        }
        finally {
            db.close();
        }
    }
    reserve(key: Uint8Array, prefix: number, crashPoint?: string): Uint8Array {
        const identity = this.identity(key, prefix), db = this.connect();
        try {
            const rows = this.validate(db), old = rows.get(identity);
            if (old === undefined || old >= Number.MAX_SAFE_INTEGER)
                throw new Error('NONCE_STATE_INVALID');
            const counter = old + 1;
            db.prepare('UPDATE nonces SET counter=? WHERE identity=?').run(counter, identity);
            this.append(identity, counter);
            if (crashPoint === 'after_witness')
                throw new Error('SYNTHETIC_CRASH_AFTER_WITNESS');
            db.exec('COMMIT');
            if (crashPoint === 'after_commit')
                throw new Error('SYNTHETIC_CRASH_AFTER_COMMIT');
            const nonce = Buffer.alloc(12);
            nonce.writeUInt32BE(prefix);
            nonce.writeBigUInt64BE(BigInt(counter), 4);
            return new Uint8Array(nonce);
        }
        finally {
            db.close();
        }
    }
}
