import * as wire from '../../../../packages/sync-protocol/src/browser';
(window as unknown as {
  __WIRE_QA__: typeof wire;
}).__WIRE_QA__=wire;
import { useState } from 'react';
import * as probe from './security';
(window as unknown as {
  __SECURITY_QA__: typeof probe;
}).__SECURITY_QA__=probe;
export function SecurityProbe() {
  const [report,setReport]=useState('尚未创建 QA key');
  return <details><summary>TEST ONLY 密钥与 nonce 能力探针</summary><p>独立数据库，随机 non-extractable AES-GCM CryptoKey。不是生产 vault、HPKE 或 Relay 封装。BLOCKED FOR NETWORK USE。</p><p>仅验证浏览器能力；不保证硬件保护、磁盘加密、同源防护、整站回滚、驱逐、断电或平台持久性。新 QA identity 不恢复旧授权。</p><button onClick={() => void probe.create().then(async (id) => {
    await probe.seal(id,'TESTONLY-diagnostic','TESTONLY-capability');
    await probe.open(id,'TESTONLY-diagnostic');
    setReport(JSON.stringify(await probe.status(id)));
  }).catch(e => setReport('BLOCKED: '+String(e)))}>显式创建新 QA identity 并验证加解密</button><p data-testid="security-report">{report}</p></details>;
}
