import './paths.mjs';
import {spawnSync} from 'node:child_process';
const result=spawnSync(process.execPath,['node_modules/@playwright/test/cli.js','install','chromium'],{stdio:'inherit',env:process.env});process.exitCode=result.status??1;
