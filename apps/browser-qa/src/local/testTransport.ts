/** Isolated fault adapter: no endpoint, no network, no IDB writes or receipts. */
export const testOnlyDisconnectedAdapter={
 async send():Promise<never>{throw Error('TEST ONLY：模拟连接失败（未发起网络请求）');},
};
