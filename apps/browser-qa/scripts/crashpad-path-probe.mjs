/** Targeted prelaunch diagnostic, not a fix or a Chromium/TLS acceptance test.
 * Official selection: chrome/common/chrome_paths_linux.cc + base/nix/xdg_util.cc.
 * DIR_CRASH_DUMPS ignores --user-data-dir: chrome/common/chrome_paths.cc.
 * CfT default product directory is google-chrome-for-testing, then Crash Reports.
 */
import {statSync,realpathSync,accessSync,constants,mkdtempSync,rmdirSync} from 'node:fs';
import {resolve,join,dirname,relative,isAbsolute} from 'node:path';
import {userInfo,platform} from 'node:os';
import {pathToFileURL} from 'node:url';
const within=(base,target)=>{const rel=relative(base,target);return rel===''||(!rel.startsWith('..'+(process.platform==='win32'?'\\':'/'))&&rel!=='..'&&!isAbsolute(rel));};
const failure=error=>['EACCES','EPERM','ENOENT','ENOTDIR','EROFS','ENOSPC'].includes(error?.code)?error.code:'UNKNOWN';
export function inspectCrashpadPath({home,env,cwd}){
 // CHROME_CONFIG_HOME present-but-empty is deliberately distinct from empty XDG.
 const selector=typeof env.CHROME_CONFIG_HOME==='string'?'CHROME_CONFIG_HOME':env.XDG_CONFIG_HOME?'XDG_CONFIG_HOME':'HOME_FALLBACK';
 const config=selector==='CHROME_CONFIG_HOME'?env.CHROME_CONFIG_HOME:selector==='XDG_CONFIG_HOME'?env.XDG_CONFIG_HOME:join(home,'.config');
 const target=resolve(cwd,config,'google-chrome-for-testing','Crash Reports');
 const out={probeKind:'NODE_FS_PRELAUNCH_CFT_PATH',selector,absolute:isAbsolute(config),homeMatchesAccount:env.HOME===home,lexicalLocation:within(home,target)?'INSIDE_HOME':'OUTSIDE_HOME',realLocation:'UNKNOWN',targetState:'MISSING',nearestType:'UNKNOWN',ancestorAccess:'UNKNOWN',createProbe:'NOT_ATTEMPTED',probeError:null};
 let nearest=target,info;
 while(true){try{info=statSync(nearest);if(nearest===target)out.targetState='EXISTS';break;}catch(error){if(!['ENOENT','ENOTDIR'].includes(error?.code)){out.targetState='INACCESSIBLE';out.probeError=failure(error);return out;}const parent=dirname(nearest);if(parent===nearest){out.probeError=failure(error);return out;}nearest=parent;}}
 out.nearestType=info.isDirectory()?'DIRECTORY':info.isFile()?'FILE':'OTHER';
 let real;
 try{real=realpathSync(nearest);out.realLocation=within(realpathSync(home),real)?'INSIDE_HOME':'OUTSIDE_HOME';accessSync(nearest,constants.W_OK|constants.X_OK);out.ancestorAccess='WRITABLE_SEARCHABLE';}catch(error){out.ancestorAccess='DENIED';out.probeError=failure(error);return out;}
 // External selected paths are observed read-only. A realpath containment check
 // bounds the sole mutation to a unique empty temporary directory in QA home.
 if(out.realLocation==='INSIDE_HOME'&&out.nearestType==='DIRECTORY'){
  let temporary;
  try{temporary=mkdtempSync(join(real,'.rh-crashpad-probe-'));out.createProbe='CREATED';rmdirSync(temporary);out.createProbe='CREATED_AND_REMOVED';}
  catch(error){out.createProbe=temporary?'CLEANUP_FAILED':'CREATE_FAILED';out.probeError=failure(error);}
 }
 return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 const account=userInfo();
 if(platform()!=='linux'||account.uid===0||process.env.HOME!==account.homedir)process.exitCode=2;
 else console.log(JSON.stringify(inspectCrashpadPath({home:account.homedir,env:process.env,cwd:process.cwd()})));
}
