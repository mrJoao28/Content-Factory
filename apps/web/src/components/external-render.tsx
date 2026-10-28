"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { API, api, send } from "@/lib/api";
import type { Project } from "@/lib/types";
import type { Act } from "./studio";
import { Button } from "./ui/button";

export function ExternalRender({project,act,busy}:{project:Project;act:Act;busy:boolean}) {
 const [download,setDownload]=useState("");
 const [hardware,setHardware]=useState(project.visual_config?.external_hardware||"GPU");
 const info=useQuery({queryKey:["external-render-info"],queryFn:()=>api<{notebook_url:string}>("/external-render/info"),staleTime:Infinity,retry:false});
 const job=project.jobs?.find(j=>j.revision===project.revision);
 const leased=Boolean(job?.owner&&job.lease_until&&new Date(job.lease_until).getTime()>Date.now());
 const waiting=job?.state==="WAITING_FOR_EXTERNAL_RENDER";
 const external=project.visual_config?.execution_location==="colab";
 const location=(execution_location:"colab"|"local")=>act(()=>send(`/projects/${project.id}/render-location`,{expected_revision:project.revision,execution_location,hardware}),"Execution location saved; completed checkpoints retained");
 return <section className="info-box" aria-label="Assisted Colab render"><h3>Assisted Colab render</h3>
 <p>Execution: {external?"Colab notebook (manual)":"local"}. Visual engine: Blender 3D. Text and voice remain on this computer.</p>
 <label>External hardware <select aria-label="External hardware" value={hardware} onChange={e=>setHardware(e.target.value as typeof hardware)}><option value="GPU">GPU · probe OptiX, then CUDA</option><option value="OPTIX">OptiX only</option><option value="CUDA">CUDA only</option><option value="CPU">CPU explicitly</option></select></label>
 <p>Pause an active production and wait for its lease to release before changing execution. Preparation retains concept/script checkpoints and stops after validated storyboard and measured audio. Exporting uses no additional inference.</p>
 {waiting&&<p role="status">Waiting for external execution/import. Progress is shown in the notebook; this application receives no live Colab progress. Resume does not start a local render.</p>}
 <div className="button-row"><Button variant="outline" disabled={busy||leased} onClick={()=>location("colab")}>Prepare for Colab</Button>
 <Button variant="outline" disabled={busy||leased||!waiting} onClick={()=>act(async()=>{const result=await send(`/projects/${project.id}/external-render/export`,{expected_revision:project.revision}) as {download_url:string};setDownload(result.download_url);},"Portable export prepared; no render or approval completed")}>Export package</Button>
 {download&&<a href={`${API}${download}`} download>Download input ZIP</a>}
 {info.data&&<a href={info.data.notebook_url} target="_blank" rel="noreferrer">Open notebook in Colab</a>}
 <Button variant="outline" disabled={busy||leased||!external} onClick={()=>location("local")}>Return to local render</Button></div>
 <label>Import result ZIP <input aria-label="Import Colab result" type="file" accept=".zip,application/zip" disabled={busy||leased||!waiting} onChange={e=>{const file=e.target.files?.[0];if(!file)return;void act(async()=>{if(file.size>256*1024**2)throw new Error("Return ZIP exceeds 256 MiB");const response=await fetch(`${API}/projects/${project.id}/external-render/import`,{method:"POST",headers:{"X-Factory-Client":"local","Content-Type":"application/zip"},body:file});if(!response.ok){const body=await response.json();throw new Error(typeof body.detail==="string"?body.detail:"Invalid return package");}},"Imported and technically validated; human review required");e.target.value="";}}/></label>
 <p>GPU and session duration are not guaranteed. Use a hosted Colab runtime and execute cells yourself. No ChatGPT or Google Cloud credentials belong in the package.</p>
 {info.error&&<p role="alert">Notebook information unavailable: {info.error.message}</p>}
 </section>;
}
