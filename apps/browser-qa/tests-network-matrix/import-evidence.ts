import {withCleanup} from '../tests-owner/cleanup.ts';
import {summarizeError} from '../scripts/network-evidence-reporter.ts';
const summary=(error:unknown)=>summarizeError(error instanceof Error?error:{message:String(error)});
/** Preserve all private causes in AggregateError; public evidence contains reviewed summaries only. */
export async function withImportCleanup(work:()=>Promise<void>,steps:(()=>void|Promise<void>)[],write:(value:unknown)=>void|Promise<void>){
 let primaryError:ReturnType<typeof summary>|null=null;const errors:ReturnType<typeof summary>[]=[];
 await withCleanup(async()=>{try{await work();}catch(error){primaryError=summary(error);throw error;}},[
  ...steps.map(step=>async()=>{try{await step();}catch(error){errors.push(summary(error));throw error;}}),
  ()=>write({state:errors.length?'FAILED':'PASS',primaryError,errors}),
 ]);
}
export function createImportFetchCounter(){
 const requests=new Map<string,string>();let preflights=0,signedPosts=0;
 return {
  request(id:string,url:string,method:string){if(url==='https://127.0.0.1:38001/v1/messages'&&['OPTIONS','POST'].includes(method))requests.set(id,method);},
  response(id:string,status:number){const method=requests.get(id);requests.delete(id);if(method==='OPTIONS'&&status===204)preflights++;if(method==='POST'&&[200,201].includes(status))signedPosts++;},
  counts:()=>({preflights,signedPosts}),
 };
}
