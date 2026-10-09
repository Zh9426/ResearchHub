// Share static tooling; select an independent business/profile/runtime origin.
const action=process.argv[2];
if(!['build','server','stop','browser','browser-stop'].includes(action))throw Error('Expected build/server/stop/browser/browser-stop');
process.env.RH_QA_PROFILE='sync';
await import(`./${action}.mjs`);
