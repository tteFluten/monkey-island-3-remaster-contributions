import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

// Credentials stay in the user's existing MCP configuration, never in browser responses.
const [root, mode, jobDir] = process.argv.slice(2);
const basement = process.env.BASEMENT_ROOT || 'E:/basement.lab';
let client;
try {
  let sdk;
  for (const dir of [path.join(root,'app'),path.join(basement,'hub')]) {
    try { const req=createRequire(path.join(dir,'package.json')); sdk=name=>import(pathToFileURL(req.resolve('@modelcontextprotocol/sdk/client/'+name+'.js')).href); await sdk('index'); break; }
    catch { sdk=null; }
  }
  if(!sdk)throw new Error('SDK_MISSING');
  let config;
  for(const file of process.env.MI3_MCP_CONFIG?[process.env.MI3_MCP_CONFIG]:[path.join(root,'.mcp.json'),path.join(basement,'.mcp.json')]) {
    try { config=JSON.parse(await fs.readFile(file,'utf8')).mcpServers?.['basement-lab'];if(config)break; }
    catch {}
  }
  if(!config)throw new Error('CONFIG_MISSING');
  const {Client}=await sdk('index');
  let transport;
  if(config.url){
    const {StreamableHTTPClientTransport}=await sdk('streamableHttp');
    transport=new StreamableHTTPClientTransport(new URL(config.url),{requestInit:{headers:config.headers||{}}});
  }else{
    const {StdioClientTransport}=await sdk('stdio');
    const args=(config.args||[]).map(arg=>process.platform==='win32'?arg.replace(/^\/mnt\/([a-z])\//i,(_,drive)=>drive.toUpperCase()+':/'):arg);
    transport=new StdioClientTransport({command:config.command,args,env:{...process.env,...config.env},stderr:'pipe'});
  }
  client=new Client({name:'monkey-sprite-workshop',version:'1.0.0'});
  await client.connect(transport);
  transport.stderr?.on('data',()=>{});
  const listed=await client.listTools();
  const tool=listed.tools.find(t=>t.name==='imagelab-generate');
  if(!tool)throw new Error('TOOL_MISSING');
  if(mode==='probe'){
    console.log(JSON.stringify({ready:true,tool:tool.name,models:tool.inputSchema?.properties?.model?.enum||[],defaultModel:tool.inputSchema?.properties?.model?.default||''}));
  }else{
    const request=JSON.parse(await fs.readFile(path.join(jobDir,mode==='alpha'?'alpha-request.json':'request.json'),'utf8'));
    const result=await client.callTool({name:tool.name,arguments:request},undefined,{timeout:600000});
    if(result.isError)throw new Error('PROVIDER_FAILED');
    const image=result.content?.find(p=>p.type==='image'&&typeof p.data==='string');
    if(!image)throw new Error('NO_IMAGE');
    const bytes=Buffer.from(image.data,'base64');if(bytes.length>48*1024*1024)throw new Error('IMAGE_TOO_LARGE');
    await fs.writeFile(path.join(jobDir,mode==='alpha'?'alpha-image.bin':'provider-image.bin'),bytes);
    console.log(JSON.stringify({ready:true,mimeType:image.mimeType||'image/png'}));
  }
}catch(error){
  const messages={SDK_MISSING:'Falta el SDK de MCP. Instalá las dependencias de app o de Basement Hub.',CONFIG_MISSING:'Falta basement-lab en .mcp.json. Configurá MI3_MCP_CONFIG o BASEMENT_ROOT.',TOOL_MISSING:'El MCP conectado no publica imagelab-generate.',NO_IMAGE:'ImageLab no devolvió una imagen. Revisá el proveedor y el modelo.',PROVIDER_FAILED:'ImageLab informó un error de generación. Revisá el proveedor antes de reintentar.',IMAGE_TOO_LARGE:'La imagen generada excede el tamaño admitido.'};
  console.log(JSON.stringify({ready:false,error:messages[error.message]||'No se pudo completar la conexión con ImageLab. Revisá el MCP, la red y las credenciales locales.'}));process.exitCode=1;
}finally{try{await client?.close();}catch{}}
