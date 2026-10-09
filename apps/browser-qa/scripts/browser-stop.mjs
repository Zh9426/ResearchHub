import {runtime} from './paths.mjs';
import {resolve} from 'node:path';
import {readFileSync} from 'node:fs';
const owner=JSON.parse(readFileSync(resolve(runtime,'browser-owner.json')));
const response=await fetch(`http://127.0.0.1:${owner.port}`,{method:'POST',headers:{'x-qa-owner':owner.token}});
if(!response.ok)throw Error('Refusing unknown browser controller');console.log('Owned QA browser close requested');
