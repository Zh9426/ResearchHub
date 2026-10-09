import {writeFileSync} from 'node:fs';
import {privateFailure} from '../scripts/native-ui-cleanup.ts';

/** Save the original bounded error tree before Playwright discards AggregateError.errors. */
export function rethrowPrivateFailure(error:unknown,path:string):never{
 try{writeFileSync(path,JSON.stringify(privateFailure(error)),{mode:0o600,flag:'wx'});}
 catch(writeError){throw new AggregateError([error,writeError],'Failure evidence persistence failed');}
 throw error;
}
