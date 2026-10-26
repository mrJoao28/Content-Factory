"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { API, api, send } from "@/lib/api";
import type { Asset, Project } from "@/lib/types";
import type { Act } from "./studio";
export function AudioMixEditor({project,act}:{project:Project;act:Act}) {
 const assets=useQuery({queryKey:["assets"],queryFn:()=>api<Asset[]>("/assets")});
 const [music,setMusic]=useState("");const [volume,setVolume]=useState(.12);const [voice,setVoice]=useState(1);const [effects,setEffects]=useState("[]");
 useEffect(()=>{const m=project.narration.mix as {music_asset_id?:string;music_volume?:number;narration_volume?:number;effects?:unknown[]}|undefined;setMusic(m?.music_asset_id||"");setVolume(m?.music_volume??.12);setVoice(m?.narration_volume??1);setEffects(JSON.stringify(m?.effects||[],null,2));},[project.id,project.revision]);
 return <details><summary>Music, sound effects and audio preview</summary>{(project.narration.path||project.narration.generated_path)?<audio controls src={`${API}/projects/${project.id}/narration`} style={{width:"100%",marginTop:16}}/>:<p className="muted">Import narration or configure Piper before preview.</p>}<form onSubmit={e=>{e.preventDefault();act(()=>send(`/projects/${project.id}/audio-mix`,{music_asset_id:music||null,music_volume:volume,narration_volume:voice,effects:JSON.parse(effects)},"PATCH"),"Audio mix saved as a new revision; resume to render it");}}><label>Background music<select value={music} onChange={e=>setMusic(e.target.value)}><option value="">No background track</option>{(assets.data||[]).filter(a=>a.kind==="music").map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>Music volume ({Math.round(volume*100)}%)<input type="range" min="0" max=".5" step=".01" value={volume} onChange={e=>setVolume(Number(e.target.value))}/></label><label>Narration volume ({Math.round(voice*100)}%)<input type="range" min=".1" max="2" step=".05" value={voice} onChange={e=>setVoice(Number(e.target.value))}/></label><label>Sound effect cues (JSON: asset_id, time in seconds, volume)<textarea className="code-editor compact" value={effects} onChange={e=>setEffects(e.target.value)}/></label><p className="muted">Available effects: {(assets.data||[]).filter(a=>a.kind==="sound-effect").map(a=>`${a.name}: ${a.id}`).join("; ")||"Import a licensed WAV/MP3 in Asset Library."}</p><Button variant="outline" type="submit">Save audio mix</Button></form></details>;
}
