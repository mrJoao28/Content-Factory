"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { Badge, type Act } from "./studio";
import { api, send } from "@/lib/api";

type Account = {id:string;label:string;connected:boolean;active:boolean;model:string|null;models:{slug:string;display_name:string}[];inference_verified:boolean};
export type ChatGPTStatus = {state:string;provider:"chatgpt"|"codex";configuration?:{source:string};accounts:Account[];active_id:string|null;message?:string;login:{id?:string;state:string;url?:string;message?:string}};
const waiting=(state?:string)=>state==="WAITING"||state==="EXCHANGING";

export function ChatGPTSettings({act}:{act:Act}) {
 const client=useQueryClient();
 const testRequest=useRef<AbortController|null>(null);
 const [testing,setTesting]=useState(false);
 useEffect(()=>()=>testRequest.current?.abort(),[]);
 const status=useQuery({queryKey:["chatgpt"],queryFn:()=>api<ChatGPTStatus>("/auth/chatgpt"),retry:false,refetchOnWindowFocus:false,refetchInterval:q=>!q.state.error&&waiting(q.state.data?.login.state)?2000:false});
 const [busy,setBusy]=useState(false);const [consent,setConsent]=useState(false);const [result,setResult]=useState("");
 const data=status.data;const active=data?.accounts.find(a=>a.active);const pending=!status.error&&waiting(data?.login.state);
 const run=(action:()=>Promise<unknown>,message:string)=>{if(busy)return;setBusy(true);act(async()=>{try{await action();await status.refetch();await client.invalidateQueries({queryKey:["preferences"]});}finally{setBusy(false);}},message);};
 const connect=(account_id?:string)=>run(()=>send("/auth/chatgpt/connect",{account_id}),"Follow the official browser authorization, then return here.");
 return <div><h2>Continue with ChatGPT</h2><p>Authorize Content Factory to generate scripts, storyboards, reviews and metadata using your ChatGPT plan. This connection does not generate images or videos.</p>
 <p className="muted">Provider source: {data?.configuration?.source||"checking"}. Saved Settings takes precedence over .env; existing productions retain their own selection.</p><label>Text provider<select aria-label="Text provider" value={data?.provider||""} disabled={!data||busy||pending} onChange={e=>{const provider=e.currentTarget.value;run(()=>send("/settings",{ai_provider:provider},"PATCH"),"Text provider selected explicitly");}}><option value="" disabled>Loading...</option><option value="chatgpt">ChatGPT plan - direct connection</option><option value="codex">Codex - compatibility provider</option></select></label>
 <Badge status={data?.state||"CHECKING"}/>{status.error&&<p role="alert">{status.error.message}</p>}{data?.message&&<p role="alert">{data.message}</p>}
 <div className="button-row"><Button disabled={busy||pending} onClick={()=>connect()}>Continue with ChatGPT</Button><Button disabled={busy||status.isFetching} variant="outline" onClick={()=>void status.refetch()}><RefreshCw size={14}/> Refresh connection</Button>{pending&&<Button disabled={busy} variant="outline" onClick={()=>run(()=>send("/auth/chatgpt/cancel",{}),"Authorization cancelled; existing connections preserved")}>Cancel authorization</Button>}</div>
 <p role="status">{pending?"Waiting for authorization. Complete sign-in in your browser or cancel.":data?.login.message}</p>
 {data?.login.url&&pending&&<a href={data.login.url} target="_blank" rel="noreferrer" className="text-link">Open official authorization manually <ExternalLink size={13}/></a>}
 {data?.accounts.map(account=><div className="publication" key={account.id}><div><strong>{account.label}</strong><small>{account.active?"Active connection":"Saved connection"} - {account.connected?"authorized":"disconnected"}</small></div><div className="button-row">{!account.active&&account.connected&&<Button disabled={busy||pending} variant="outline" onClick={()=>run(()=>send(`/auth/chatgpt/accounts/${account.id}/activate`,{}),"ChatGPT connection selected; earlier generations cancelled")}>Use account</Button>}<Button disabled={busy||pending} variant="outline" onClick={()=>connect(account.id)}>Reconnect</Button>{account.connected&&<Button disabled={busy||pending} variant="ghost" onClick={()=>run(async()=>{const r=await send<{message:string}>(`/auth/chatgpt/accounts/${account.id}/disconnect`,{});setResult(r.message);},"Local disconnect completed; inspect remote revocation status below")}>Disconnect</Button>}</div></div>)}
 {active?.connected&&<><h3>Model and access</h3><p>Active account: {active.label}. Model: {active.model||"not selected"}. Login {data?.state==="EXPIRED"?"needs renewal":"authorized"}; inference {active.inference_verified?"verified for the selected model":"not verified"}.</p><Button disabled={busy||pending} variant="outline" onClick={()=>run(()=>send(`/auth/chatgpt/accounts/${active.id}/models`,{}),"Authenticated model catalog refreshed")}>Refresh model catalog</Button><label>ChatGPT model<select aria-label="ChatGPT model" disabled={busy||pending} value={active.model||""} onChange={e=>{const model=e.currentTarget.value;setConsent(false);setResult("");run(()=>send(`/auth/chatgpt/accounts/${active.id}/model`,{model}),"Model selected; a completed generation confirms access");}}><option value="" disabled>Choose an available model</option>{active.models.map(m=><option key={m.slug} value={m.slug}>{m.display_name}</option>)}</select></label>{!active.models.length&&<p>No models are cached. Refresh the catalog. Availability depends on this account.</p>}<label className="check-label"><input type="checkbox" disabled={busy||pending||!active.model} checked={consent} onChange={e=>setConsent(e.target.checked)}/>I understand that testing this connection consumes my ChatGPT plan allowance.</label><Button disabled={!consent||busy||pending||!active.model} variant="outline" onClick={()=>run(async()=>{setResult("");const controller=new AbortController();testRequest.current=controller;setTesting(true);try{const r=await api<{state:string;model:string}>("/auth/chatgpt/test",{method:"POST",body:JSON.stringify({confirm_plan_usage:true}),signal:controller.signal});setResult(`Inference ${r.state} for ${r.model}`);}catch(error){if(controller.signal.aborted)setResult("Text generation test cancelled.");else throw error;}finally{setTesting(false);testRequest.current=null;}},"Text inference completed and validated")}>Test text generation</Button>{testing&&<Button variant="outline" onClick={()=>testRequest.current?.abort()}>Cancel text test</Button>}</>}
 {result&&<p role="status">{result}</p>}<p className="muted">New productions retain their selected provider, connection and model. Reconnecting and Resume preserves completed checkpoints. No API key or Codex installation is required for the direct provider.</p><a className="text-link" href="https://chatgpt.com/#settings/Usage" target="_blank" rel="noreferrer">Manage ChatGPT plan usage <ExternalLink size={13}/></a><hr/></div>;
}

export function TextConnectionIndicator() {
 const connection=useQuery({queryKey:["chatgpt"],queryFn:()=>api<ChatGPTStatus>("/auth/chatgpt"),retry:false,refetchOnWindowFocus:false});
 const data=connection.data;const active=data?.accounts.find(a=>a.active);
 return <p className="composer-note">Text provider: {data?.provider||"checking"}{data?.provider==="chatgpt"?` / ${active?.label||"connect in Settings"} / ${active?.model||"choose a model"}`:" / official Codex session"}</p>;
}
