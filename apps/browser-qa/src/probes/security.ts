/** Isolated synthetic capability probe. Never a production vault or Relay envelope. */
const DB='researchhub-TESTONLY-security-v1';
// Assigned by this synthetic test authority fixture; never a production registration.
const AUTHORITY={ scope: 'TESTONLY synthetic authority',prefix: 0x51410001 } as const;
type Identity={
  id: string;
  key: CryptoKey;
  marker: string;
  high: number;
};
type Ledger={
  id: string;
  marker: string;
  counter: number;
  prefix: number;
};
type Envelope={
  format: 'TESTONLY-AES-GCM-v1';
  identity: string;
  action: string;
  digest: string;
  nonce: string;
  aad: string;
  ciphertext: string;
};
type Action={
  id: string;
  digest: string;
  state: 'pending'|'complete';
  envelope?: Envelope;
};
const hex=(b: ArrayBuffer|Uint8Array) => Array.from(b instanceof Uint8Array? b:new Uint8Array(b),x => x.toString(16).padStart(2,'0')).join('');
const bytes=(s: string) => Uint8Array.from(s.match(/../g)??[],x => parseInt(x,16));
const encode=(s: string) => new TextEncoder().encode(s);
async function database() {
  return new Promise<IDBDatabase>((ok,no) => {
    const r=indexedDB.open(DB,1);
    r.onupgradeneeded=() => {
      for(const name of ['keys','ledger','actions'])
        r.result.createObjectStore(name,{ keyPath: 'id' });
    };
    r.onsuccess=() => ok(r.result);
    r.onerror=() => no(r.error);
  });
}
/** All reads/writes are scheduled via IDB callbacks; no crypto/network awaits in a live transaction. */
async function mutate<T>(names: string[],body: (tx: IDBTransaction,done: (value: T) => void) => void): Promise<T> {
  const db=await database();
  return new Promise((ok,no) => {
    const tx=db.transaction(names,'readwrite');
    let value: T;
    let failure: unknown;
    tx.oncomplete=() => {
      db.close();
      ok(value);
    };
    tx.onabort=() => {
      db.close();
      no(failure??tx.error??Error('QA transaction aborted'));
    };
    try {

      body(tx,v => {
        value=v;
      });

    }
    catch(e) {

      failure=e;

      tx.abort();

    }
  });
}
// The mirrored high-water value detects a partial ledger rewind only. A coherent
// rollback of every record remains undetectable here and blocks all network use.
function readPair(tx: IDBTransaction,id: string,accept: (key: Identity,ledger: Ledger) => void) {
  const k=tx.objectStore('keys').get(id);
  k.onsuccess=() => {
    const l=tx.objectStore('ledger').get(id);
    l.onsuccess=() => {
      const key=k.result as Identity,ledger=l.result as Ledger;
      if(!key||!(key.key instanceof CryptoKey)||key.key.extractable||key.key.algorithm.name!=='AES-GCM'||(key.key.algorithm as AesKeyAlgorithm).length!==256||key.key.type!=='secret'||key.key.usages.length!==2||!key.key.usages.includes('encrypt')||!key.key.usages.includes('decrypt')||key.id!==id||typeof key.marker!=='string'||!/^[0-9a-f-]{36}$/.test(key.marker)||!ledger||ledger.id!==id||ledger.marker!==key.marker||ledger.counter!==key.high||!Number.isSafeInteger(ledger.counter)||ledger.counter<0||ledger.prefix!==AUTHORITY.prefix) {

        tx.abort();

        return;

      }
      accept(key,ledger);
    };
  };
}
export async function create() {
  const key=await crypto.subtle.generateKey({ name: 'AES-GCM',length: 256 },false,['encrypt','decrypt']);
  const id=crypto.randomUUID(),marker=crypto.randomUUID();
  await mutate<void>(['keys','ledger'],(tx,done) => {
    tx.objectStore('keys').add({ id,key,marker,high: 0 });
    tx.objectStore('ledger').add({ id,marker,counter: 0,prefix: AUTHORITY.prefix });
    done();
  });
  return id;
}
export async function status(id: string) {
  return mutate(['keys','ledger'],(tx,done) => readPair(tx,id,(key,l) => done({ id,counter: l.counter,extractable: key.key.extractable,network: 'BLOCKED FOR NETWORK USE',authority: AUTHORITY.scope })));
}
export async function seal(id: string,action: string,payload: string): Promise<Envelope> {

  if(!action.startsWith('TESTONLY-')||!payload.startsWith('TESTONLY-'))
    throw Error('TESTONLY input required');

  const digest=hex(await crypto.subtle.digest('SHA-256',encode(payload)));

  const actionId=id+':'+action;

  const reserved=await mutate<{
    cached?: Envelope;
    key?: CryptoKey;
    nonce?: string;
  }>(['keys','ledger','actions'],(tx,done) => readPair(tx,id,(key,l) => {
    const actions=tx.objectStore('actions');
    const r=actions.get(actionId);
    r.onsuccess=() => {
      const old=r.result as Action|undefined;
      if(old) {

        if(old.digest!==digest||old.state!=='complete'||!old.envelope) {

          tx.abort();

          return;

        }

        done({ cached: old.envelope,key: key.key });

        return;

      }
      if(l.counter>=Number.MAX_SAFE_INTEGER) {

        tx.abort();

        return;

      }
      l.counter++;
      key.high=l.counter;
      const nonce=new Uint8Array(12);
      const view=new DataView(nonce.buffer);
      view.setUint32(0,l.prefix,false);
      view.setBigUint64(4,BigInt(l.counter),false);
      tx.objectStore('keys').put(key);
      tx.objectStore('ledger').put(l);
      actions.add({ id: actionId,digest,state: 'pending' });
      done({ key: key.key,nonce: hex(nonce) });
    };
  }));

  if(reserved.cached) {

    await verifyEnvelope(reserved.cached,reserved.key!,id,action,digest);

    return reserved.cached;

  }

  // Reservation is committed before invoking encryption. Failures leave a burned counter + pending action.
  const aad=JSON.stringify({ format: 'TESTONLY-AES-GCM-v1',identity: id,action,digest });

  const ciphertext=hex(await crypto.subtle.encrypt({ name: 'AES-GCM',iv: bytes(reserved.nonce!),additionalData: encode(aad) },reserved.key!,encode(payload)));

  const envelope: Envelope={ format: 'TESTONLY-AES-GCM-v1',identity: id,action,digest,nonce: reserved.nonce!,aad,ciphertext };

  await mutate<void>(['keys','ledger','actions'],(tx,done) => readPair(tx,id,() => {
    const r=tx.objectStore('actions').get(actionId);
    r.onsuccess=() => {
      if(r.result?.state!=='pending'||r.result.digest!==digest) {

        tx.abort();

        return;

      }
      tx.objectStore('actions').put({ id: actionId,digest,state: 'complete',envelope });
      done();
    };
  }));

  return envelope;

}
export async function open(id: string,action: string) {
  const stored=await mutate<{
    key: CryptoKey;
    e: Envelope;
  }>(['keys','ledger','actions'],(tx,done) => readPair(tx,id,key => {
    const r=tx.objectStore('actions').get(id+':'+action);
    r.onsuccess=() => {
      if(r.result?.state!=='complete') {

        tx.abort();

        return;

      }
      done({ key: key.key,e: r.result.envelope });
    };
  }));
  return verifyEnvelope(stored.e,stored.key,id,action,stored.e.digest);
}
export function importLedger(): never {
  throw Error('BLOCKED: importing an old nonce ledger is forbidden');
}
async function verifyEnvelope(e: Envelope,key: CryptoKey,id: string,action: string,digest: string): Promise<string> {

  if(!e||Object.keys(e).sort().join(',')!=='aad,action,ciphertext,digest,format,identity,nonce'||e.format!=='TESTONLY-AES-GCM-v1'||e.identity!==id||e.action!==action||e.digest!==digest||!/^[0-9a-f]{64}$/.test(digest)||!/^[0-9a-f]{24}$/.test(e.nonce)||!/^(?:[0-9a-f]{2}){16,}$/.test(e.ciphertext))
    throw Error('corrupt QA envelope');

  const nonce=bytes(e.nonce),view=new DataView(nonce.buffer);

  const counter=view.getBigUint64(4,false);

  if(view.getUint32(0,false)!==AUTHORITY.prefix||counter<1n||counter>BigInt(Number.MAX_SAFE_INTEGER))
    throw Error('invalid QA nonce');

  if(e.aad!==JSON.stringify({ format: e.format,identity: id,action,digest }))
    throw Error('QA envelope binding mismatch');

  const plaintext=await crypto.subtle.decrypt({ name: 'AES-GCM',iv: nonce,additionalData: encode(e.aad) },key,bytes(e.ciphertext));

  if(hex(await crypto.subtle.digest('SHA-256',plaintext))!==digest)
    throw Error('QA payload digest mismatch');

  return new TextDecoder('utf-8',{ fatal: true }).decode(plaintext);

}
