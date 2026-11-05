import {build} from 'esbuild';
import {mkdir, writeFile, copyFile, mkdtemp, rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {join, resolve, dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const out = join(root,'outputs/connectors');
const market = join(out,'marketplace');
const plugin = join(market,'plugins/poach');
const entry = join(plugin,'server.mjs');
const stage = await mkdtemp(join(tmpdir(),'poach-extension-'));
const json = async (path, data) => {
  await mkdir(dirname(path),{recursive:true});
  await writeFile(path, JSON.stringify(data,null,2)+'\n');
};
const metadata = {name:'poach', version:'0.1.0', description:'Read the screen capture, keyframes, and timestamped notes you share from Poach.'};
try {
  await mkdir(plugin,{recursive:true});
  await build({entryPoints:[resolve(root,'packages/mcp-server/dist/index.js')],outfile:entry,bundle:true,platform:'node',format:'esm',banner:{js:"import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);"},target:'node20'});
  const env = {PATH:[dirname(process.execPath),'/opt/homebrew/bin','/usr/local/bin','/usr/bin','/bin'].join(':')};
  await json(join(market,'.agents/plugins/marketplace.json'),{name:'poach-local',plugins:[{name:'poach',source:{source:'local',path:'./plugins/poach'},policy:{installation:'AVAILABLE',authentication:'ON_INSTALL'},category:'Productivity'}]});
  await json(join(plugin,'.codex-plugin/plugin.json'),{...metadata,mcpServers:'./.mcp.json'});
  // This local marketplace targets the machine on which it is built.
  await json(join(plugin,'.mcp.json'),{mcpServers:{poach:{command:process.execPath,args:[entry],env}}});
  await copyFile(entry,join(stage,'server.mjs'));
  await json(join(stage,'manifest.json'),{manifest_version:'0.3',...metadata,display_name:'Poach',author:{name:'Poach'},server:{type:'node',entry_point:'server.mjs',mcp_config:{command:'node',args:['${__dirname}/server.mjs'],env}},compatibility:{platforms:['darwin']}});
  const archive=join(out,'Poach.mcpb');
  await rm(archive,{force:true});
  execFileSync('zip',['-q',archive,'manifest.json','server.mjs'],{cwd:stage});
  console.log(market+'\n'+archive);
} finally { await rm(stage,{recursive:true,force:true}); }
