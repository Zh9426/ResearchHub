import {createServer} from 'node:http';
import {readFileSync,writeFileSync,existsSync,unlinkSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {resolve} from 'node:path';
import {dist,runtime,origin,route} from './paths.mjs';
const token=randomUUID();
const assets={'/app.js':'text/javascript','/app.css':'text/css','/icon.svg':'image/svg+xml','/sw.js':'text/javascript'};
const server=createServer((req,res)=>{
 if(req.headers.host!=='127.0.0.1:3313'){res.writeHead(403);return res.end();}
 if(req.url==='/__qa_stop'&&req.method==='POST'&&req.headers['x-qa-owner']===token){res.end('stopping');server.close();return;}
 if(req.method!=='GET'){res.writeHead(405);return res.end();}
 const path=new URL(req.url,origin).pathname;
 const file=assets[path]?path.slice(1):route(path)?'index.html':null;
 if(!file){res.writeHead(404);return res.end();}
 try{const body=readFileSync(resolve(dist,file));res.writeHead(200,{'Content-Type':assets[path]||'text/html','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});res.end(body);}catch{res.writeHead(503);res.end('Build QA first');}
});
server.on('error',error=>{console.error(`QA refuses listener: ${error.message}`);process.exitCode=1;});
server.on('close',()=>{const path=resolve(runtime,'server-owner.json');if(existsSync(path)&&JSON.parse(readFileSync(path)).token===token)unlinkSync(path);});
server.listen(3313,'127.0.0.1',()=>{writeFileSync(resolve(runtime,'server-owner.json'),JSON.stringify({token,pid:process.pid,origin}));console.log(`QA_READY ${origin}`);});
