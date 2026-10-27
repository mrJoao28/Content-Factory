"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { API, api, send } from "@/lib/api";
import type { Project } from "@/lib/types";
import type { Act } from "./studio";
import { Button } from "./ui/button";

export type VisualChoice = {engine:"compositor_2d"|"blender_3d";quality:"preview"|"final";character:"dino"|"milo";environment:"magic_forest"|"dusk_garden"|"engineering_studio";resolution:"360x640"|"720x1280"|"1080x1920";fps:24|30};
export const defaultVisual:VisualChoice = {engine:"compositor_2d",quality:"preview",character:"dino",environment:"magic_forest",resolution:"360x640",fps:24};
type Readiness = {blender:{state:string;message:string;version?:string};voice:{state:string;message?:string;note?:string;model?:string}};
export function VisualOptions({value,onChange}:{value:VisualChoice;onChange:(v:VisualChoice)=>void}) {
 const {data,error} = useQuery({queryKey:["visual-catalog"],queryFn:()=>api<Readiness>("/visual/catalog"),refetchInterval:false,staleTime:60000,retry:false});
 const set = (patch:Partial<VisualChoice>) => onChange({...value,...patch});
 return <div className="info-box"><label>Visual engine <select aria-label="Visual engine" value={value.engine} onChange={e=>set({engine:e.target.value as VisualChoice["engine"]})}><option value="compositor_2d">2D / 2.5D compositor</option><option value="blender_3d">3D local · Blender CPU</option></select></label>{value.engine==="blender_3d"&&<>
 <label>Character <select aria-label="3D character" value={value.character} onChange={e=>set({character:e.target.value as VisualChoice["character"]})}><option value="dino">Dino · dino-v1</option><option value="milo">Milo · milo-v1</option></select></label>
 <label>Environment <select aria-label="3D environment" value={value.environment} onChange={e=>set({environment:e.target.value as VisualChoice["environment"]})}><option value="magic_forest">Magic forest</option><option value="dusk_garden">Dusk garden</option><option value="engineering_studio">Engineering studio</option></select></label>
 <label>Quality <select aria-label="Render quality" value={value.quality} onChange={e=>set({quality:e.target.value as VisualChoice["quality"]})}><option value="preview">Preview · 8 CPU samples</option><option value="final">Final · 32 CPU samples</option></select></label>
 <label>Resolution <select aria-label="3D resolution" value={value.resolution} onChange={e=>set({resolution:e.target.value as VisualChoice["resolution"]})}><option>360x640</option><option>720x1280</option><option>1080x1920</option></select></label>
 <label>FPS <select aria-label="3D FPS" value={value.fps} onChange={e=>set({fps:Number(e.target.value) as 24|30})}><option>24</option><option>30</option></select></label>
 <p>Blender: {data?.blender.state||"Checking"}. {data?.blender.message||error?.message}</p><p>Voice: {data?.voice.state||"Checking"}. {data?.voice.model||data?.voice.message} You can import narration in Review studio.</p><p>Render a Preview first and inspect its framing and motion. CPU rendering can be slow on an 8 GB notebook. ChatGPT generates planning text; Blender generates the pictures locally.</p></>}</div>;
}

export function VisualProduction({project,act,busy}:{project:Project;act:Act;busy:boolean}) {
 const [confirmed,setConfirmed]=useState(false);
 const [visual,setVisual]=useState<VisualChoice>({...defaultVisual,...project.visual_config});
 useEffect(()=>{setVisual({...defaultVisual,...project.visual_config});setConfirmed(false);},[project.id,project.revision,project.visual_config]);
 const job=project.jobs?.find(j=>j.revision===project.revision);
 const cp=job?.checkpoint||{};
 const steps=[['creative_director','Concept'],['script_writer','Script'],['storyboard_planner','Planning'],['visual_director','Assets'],['audio','Audio']];
 return <section className="panel pad"><h3>Visual production · {project.visual_config?.engine==="blender_3d"?"3D local":"2D / 2.5D"}</h3><p>{project.target_duration}s · revision {project.revision} · {project.visual_config?.quality||"legacy"}. Current stage: {job?.state||project.status}</p>
 <ol>{steps.map(([key,label])=><li key={key}>{label}: {cp[key]?"validated checkpoint":job?.state==="FAILED"?"pending / interrupted":"pending"}</li>)}<li>Render: {project.artifacts?.some(a=>a.revision===project.revision)?"validated file, human review required":"pending"}</li></ol>
 <VisualOptions value={visual} onChange={setVisual}/>
 <p>Regeneration retains the concept and script. It invalidates storyboard, visual/animation reviews, audio composition, publishing metadata, renders and approval. Previous revision files remain available on disk. Text regeneration uses the selected plan allowance.</p>
 <label className="check-label"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I confirm this invalidation and text generation.</label>
 <div className="button-row"><Button variant="outline" disabled={busy||!confirmed} onClick={()=>act(()=>send(`/projects/${project.id}/visual/regenerate`,{expected_revision:project.revision,confirm_invalidation:true}),"Planning queued; concept and script retained")}>Regenerate planning</Button>
 <Button variant="outline" disabled={busy||!confirmed} onClick={()=>act(()=>send(`/projects/${project.id}/visual/settings`,{expected_revision:project.revision,confirm_invalidation:true,visual}),"New visual revision queued")}>Apply visual settings and regenerate</Button></div></section>;
}

export function VoiceTest() {
 const [url,setUrl]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
 useEffect(()=>()=>{if(url)URL.revokeObjectURL(url);},[url]);
 return <div className="info-box"><h3>Local English voice</h3><p>Set PIPER_PATH and PIPER_VOICE_PATH in your local .env, restart the API, then test. No download or plan usage occurs.</p><Button variant="outline" disabled={busy} onClick={async()=>{setBusy(true);setError("");try{const response=await fetch(`${API}/visual/voice-test`,{method:"POST",headers:{"X-Factory-Client":"local"}});if(!response.ok){const body=await response.json();throw new Error(typeof body.detail==="string"?body.detail:"Voice test failed");}setUrl(URL.createObjectURL(await response.blob()));}catch(e){setError(e instanceof Error?e.message:"Voice test failed");}finally{setBusy(false);}}}>{busy?"Synthesizing locally...":"Test configured voice"}</Button>{error&&<p role="alert">{error}</p>}{url&&<audio aria-label="Voice sample" controls src={url}/>}</div>;
}
