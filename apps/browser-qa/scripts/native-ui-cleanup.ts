import {withCleanup} from '../tests-owner/cleanup.ts';
/** Public output is independent of which UI operation or unmount failed. */
export const NATIVE_UI_FAILURE='NATIVE_UI_LABEL_ASSERTION_FAILED';
export async function withNativeUiCleanup(work:()=>Promise<void>,cleanup:()=>void|Promise<void>){await withCleanup(work,[cleanup]);}
/** Ignored private evidence only. Preserve nested errors and causes, bound cycles/depth. */
type PrivateFailure={name:string;message:string;stack?:string;errors?:PrivateFailure[];omittedErrors?:number;cause?:PrivateFailure};
export function privateFailure(error:unknown,depth=0,seen=new Set<unknown>()):PrivateFailure{
 if(depth>=8||seen.has(error))return {name:'BoundedError',message:'DETAIL_LIMIT'};
 if(!(error instanceof Error))return {name:'ThrownValue',message:String(error)};
 seen.add(error);
 const result:PrivateFailure={name:error.name,message:error.message,stack:error.stack};
 if(error instanceof AggregateError){result.errors=error.errors.slice(0,32).map(value=>privateFailure(value,depth+1,seen));if(error.errors.length>32)result.omittedErrors=error.errors.length-32;}
 if(error.cause!==undefined)result.cause=privateFailure(error.cause,depth+1,seen);
 seen.delete(error);return result;
}
