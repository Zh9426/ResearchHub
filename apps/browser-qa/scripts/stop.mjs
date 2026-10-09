import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {runtime,origin} from './paths.mjs';
const owner=JSON.parse(readFileSync(resolve(runtime,'server-owner.json')));
const response=await fetch(`${origin}/__qa_stop`,{method:'POST',headers:{'x-qa-owner':owner.token}});
if(!response.ok)throw Error('Refusing unknown server');console.log('Owned QA server stopped');
