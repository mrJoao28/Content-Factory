import { expect, test } from "@playwright/test";

test("Music Studio persists a real plan, shows import and paid consent, and cancels queued work",async({page,request})=>{
 const base="http://127.0.0.1:8001",headers={"X-Factory-Client":"local"};
 const response=await request.post(`${base}/projects`,{headers,data:{idea:"An original educational music browser fixture about helping friends",channel_id:"wondernest",target_duration:8,musical_format:"musical_story",visual:{engine:"blender_3d",execution_location:"colab"}}});
 expect(response.ok()).toBeTruthy();const project=await response.json();expect(project.status).toBe("WAITING_FOR_MUSIC");
 await page.addInitScript(id=>{localStorage.setItem("factory-project",id);localStorage.setItem("factory-channel","wondernest");},project.id);
 await page.goto("/preview");
 const studio=page.getByRole("region",{name:"Music Studio"});await expect(studio).toBeVisible();
 await studio.getByText("Lyrics, timeline and animation events",{exact:true}).click();
 const plan={format:"musical_story",educational_goal:"Help a friend",characters:["dino"],environment:"magic_forest",beginning:"Dino sees a friend",development:"He offers help",conclusion:"Both are happy",segments:[{id:"help",title:"Little helping hands",kind:"song",duration:8,visible_action:"Dino waves and smiles",sections:[{kind:"verse",duration:4,lines:["Little hands can help a friend"]},{kind:"chorus",duration:4,lines:["Help and smile, again, again"]}]}]};
 await studio.getByRole("textbox",{name:"Music plan JSON"}).fill(JSON.stringify(plan));
 await studio.getByRole("button",{name:"Save musical revision",exact:true}).click();
 await expect(studio.getByRole("heading",{name:/Little helping hands/})).toBeVisible();
 await expect(studio.getByRole("button",{name:"Generate sung song (paid)",exact:true})).toBeDisabled();
 await expect(studio.getByRole("button",{name:"Mix and validate final PCM16 WAV",exact:true})).toBeDisabled();
 await expect(studio.getByText("audio_required",{exact:true})).toBeVisible();
 await studio.getByText("Track volumes and fades (save musical revision to apply)",{exact:true}).click();
 await studio.getByRole("spinbutton",{name:"Voice / complete song / solo instrumental volume",exact:true}).fill("0.6");
 await studio.getByRole("button",{name:"Save musical revision",exact:true}).click();
 await expect.poll(async()=>{const detail=await(await request.get(`${base}/projects/${project.id}`)).json();return detail.music_plan.segments[0].gain;}).toBe(0.6);
 await studio.getByRole("button",{name:"Generate local instrumental",exact:true}).click();
 await expect(studio.getByRole("button",{name:"Pause / cancel music operation",exact:true})).toBeVisible();
 await studio.getByRole("button",{name:"Pause / cancel music operation",exact:true}).click();
 const current=await(await request.get(`${base}/projects/${project.id}`)).json();
 expect(current.jobs[0].state).toBe("PAUSED");expect(current.jobs[0].checkpoint._music_operation).toBeUndefined();
 await page.screenshot({path:"../../output/music-studio-browser.png",fullPage:true});
});
