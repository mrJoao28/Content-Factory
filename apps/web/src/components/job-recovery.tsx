"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, send } from "@/lib/api";
import type { Job } from "@/lib/types";
import type { ChatGPTStatus } from "./chatgpt-settings";
import type { Act } from "./studio";
import { Button } from "./ui/button";

type Selection = {provider?:string;account_id?:string|null;model?:string|null};
const describe=(s?:Selection|null)=>s?`${s.provider} / ${s.account_id||"no direct account"} / ${s.model||"provider default"}`:"Unresolved legacy selection: explicit choice required";
export function JobRecovery({job,act}:{job:Job;act:Act}) {
 const connection=useQuery({queryKey:["chatgpt"],queryFn:()=>api<ChatGPTStatus>("/auth/chatgpt"),retry:false,refetchOnWindowFocus:false});
 const [consent,setConsent]=useState(false);const [busy,setBusy]=useState(false);
 const data=connection.data;const account=data?.accounts.find(a=>a.active);
 const current=job.diagnostic?.selection??job.checkpoint._ai_selection as Selection|undefined;
 const next:Selection|undefined=data?.provider==="chatgpt"?{provider:"chatgpt",account_id:account?.id,model:account?.model}:data?{provider:"codex"}:undefined;
 const waiting=/WAITING|FAILED|PAUSED/.test(job.state);
 const ready=!!next&&(next.provider==="codex"||!!(account?.connected&&account.model));
 return <section className="info-box" aria-label="Production text selection">
 <p><strong>Production text connection:</strong> {describe(current)}</p><p>Selection evidence: {job.diagnostic?.selection_source||"checkpoint"}.</p>
 <p>Global provider for new productions: {data?.provider||"checking"}. Source: {data?.configuration?.source||job.diagnostic?.global.source||"checking"}.</p>
 <p className="muted">Saved Settings takes precedence over .env. Existing productions retain their own selection.</p>
 {job.error&&<div role="alert"><strong>Production interrupted: {job.diagnostic?.stage||"stage not recorded"}</strong><p>{job.error}</p><p>{job.diagnostic?.next_action||"Review the configuration before resuming."}</p></div>}
 {waiting&&<><p>New selection: {describe(next)}</p>
 {current?.provider!==next?.provider&&<p>This production keeps its previous provider until you explicitly apply the new selection.</p>}
 {!!job.diagnostic?.completed_steps.length&&<p>Completed checkpoints are retained and may have been produced by another model: {job.diagnostic.completed_steps.join(", ")}.</p>}
 {!ready&&<p>Connect and choose an available model in <a href="/settings">Settings</a>, then return here.</p>}
 <label className="check-label"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>I confirm the selection above. Text generation uses the selected plan allowance.</label>
 <Button disabled={!ready||!consent||busy} onClick={()=>{if(busy)return;setBusy(true);act(async()=>{try{await send(`/projects/${job.project_id}/text-selection`,{confirm_plan_usage:true,resume:true,expected_selection:next});setConsent(false);}finally{setBusy(false);}},"Text selection applied and production resumed; completed checkpoints retained");}}>{next?.provider==="chatgpt"?"Use selected ChatGPT and resume":"Use selected provider and resume"}</Button></>}
 </section>;
}
