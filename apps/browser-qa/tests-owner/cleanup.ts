export async function withCleanup(work:()=>Promise<void>,steps:(()=>void|Promise<void>)[]){
 const errors:unknown[]=[];
 try{await work();}catch(error){errors.push(error);}
 for(const step of steps){try{await step();}catch(error){errors.push(error);}}
 if(errors.length)throw new AggregateError(errors,'Owner UI operation or owned cleanup failed');
}
