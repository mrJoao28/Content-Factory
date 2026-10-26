import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
test("real dashboard, project creation, queue and independent channels",async({page})=>{
 await page.goto("/");
 await expect(page.getByRole("heading",{name:"Production overview"})).toBeVisible();
 await expect(page.getByRole("heading",{name:"A blank canvas, ready for your ideas"})).toBeVisible();
 await page.getByRole("button",{name:"New production"}).click();
 await page.getByRole("textbox",{name:"Production idea"}).fill("A little robot discovers a magical garden and learns to share.");
 await page.getByRole("button",{name:"Start production"}).click();
 await expect(page.getByText("Production created",{exact:true})).toBeVisible();
 await expect(page.getByText("Idea accepted and queued")).toBeVisible();
 await page.getByRole("link",{name:"Production queue"}).click();
 await expect(page.getByRole("button",{name:/A little robot discovers/})).toBeVisible();
 await page.getByRole("button",{name:"Pause",exact:true}).click();
 await expect(page.getByText("Pause requested",{exact:true})).toBeVisible();
 await page.getByRole("button",{name:"How It Actually Works",exact:true}).click();
 await expect(page.getByRole("heading",{name:"A blank canvas, ready for your ideas"})).toBeVisible();
 await page.getByRole("button",{name:"New production"}).click();
 await page.getByRole("textbox",{name:"Production idea"}).fill("Explain how expansion joints let a bridge move as temperatures change.");
 await page.getByRole("button",{name:"Start production"}).click();
 await expect(page.getByText("Production created",{exact:true})).toBeVisible();
 await page.screenshot({path:"../../output/studio-workspace.png",fullPage:true});
});
test("library creates a real reusable series",async({page})=>{
 await page.goto("/series");
 await page.getByRole("textbox",{name:"Name",exact:true}).fill("Ocean Explorers");
 await page.getByRole("button",{name:"Create series",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Ocean Explorers",exact:true})).toBeVisible();
});
test("review does not enable approval without a real render",async({page})=>{
 await page.goto("/preview");
 await expect(page.getByRole("heading",{name:"Choose a production"})).toBeVisible();
 await expect(page.getByRole("button",{name:"Approve video"})).toHaveCount(0);
});

test("settings exposes real Codex login status and device-code fallback",async({page})=>{
 await page.goto("/settings");
 await expect(page.getByRole("heading",{name:"Codex compatibility login",exact:true})).toBeVisible();
 await expect(page.getByRole("button",{name:"Use device code",exact:true})).toBeVisible();
 await expect(page.getByRole("button",{name:"Verify login",exact:true})).toBeVisible();
 await expect(page.getByText("codex login --device-auth",{exact:true})).toBeVisible();
});


test("direct ChatGPT authorization UI cancels, recovers and requests explicit plan test consent",async({page})=>{
 let login={state:"IDLE",url:undefined as string|undefined,message:""};
 let model:string|null=null;let verified=false;let error=false;let connected=false;
 const account={id:"fixture-account",label:"Fixture account / workspace",connected:true,active:true,models:[{slug:"fixture-model",display_name:"Account model"}]};
 await page.route("**/auth/chatgpt",async route=>{
  if(error){await route.fulfill({status:503,json:{detail:"ChatGPT temporarily unavailable. Retry later."}});return;}
  await route.fulfill({json:{state:connected?"CONNECTED":"DISCONNECTED",provider:"chatgpt",active_id:connected?account.id:null,accounts:connected?[{...account,model,inference_verified:verified}]:[],login}});
 });
 await page.route("**/auth/chatgpt/connect",async route=>{login={state:"WAITING",url:"https://auth.openai.com/api/accounts/authorize?state=fixture",message:""};await route.fulfill({json:login});});
 await page.route("**/auth/chatgpt/cancel",async route=>{login={state:"CANCELLED",url:undefined,message:"Authorization cancelled. Existing connections were preserved."};await route.fulfill({json:login});});
 await page.route("**/auth/chatgpt/accounts/*/model",async route=>{model=route.request().postDataJSON().model;await route.fulfill({json:{}});});
 await page.route("**/auth/chatgpt/test",async route=>{expect(route.request().postDataJSON()).toEqual({confirm_plan_usage:true});verified=true;await route.fulfill({json:{state:"VERIFIED",model:"fixture-model"}});});
 await page.goto("/settings");
 await page.getByRole("button",{name:"Continue with ChatGPT",exact:true}).click();
 await expect(page.getByRole("link",{name:"Open official authorization manually"})).toBeVisible();
 await page.getByRole("button",{name:"Cancel authorization",exact:true}).click();
 await expect(page.getByText("Authorization cancelled. Existing connections were preserved.",{exact:true})).toBeVisible();
 await expect(page.getByRole("link",{name:"Open official authorization manually"})).toHaveCount(0);
 error=true;await page.getByRole("button",{name:"Refresh connection",exact:true}).click();
 await expect(page.getByRole("alert").filter({hasText:"temporarily unavailable"})).toBeVisible();
 error=false;connected=true;login={state:"COMPLETE",url:undefined,message:"Authorized; inference not verified."};
 await page.getByRole("button",{name:"Refresh connection",exact:true}).click();
 await page.getByRole("combobox",{name:"ChatGPT model",exact:true}).selectOption("fixture-model");
 const testButton=page.getByRole("button",{name:"Test text generation",exact:true});
 await expect(testButton).toBeDisabled();
 await page.getByRole("checkbox",{name:/testing this connection consumes/}).check();
 await testButton.click();
 await expect(page.getByText("Inference VERIFIED for fixture-model",{exact:true})).toBeVisible();
 const storage=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));
 expect(storage).not.toContain("access_token");expect(storage).not.toContain("refresh_token");
});


test("failed production switches explicitly to ChatGPT and resumes through real API routes",async({page,request})=>{
 test.skip(process.platform!=="win32","Browser fixture requires the Windows DPAPI vault; no plaintext fallback.");
 const base="http://127.0.0.1:8001";const headers={"X-Factory-Client":"local"};
 await request.patch(base+"/settings",{headers,data:{ai_provider:"codex"}});
 const created=await request.post(base+"/projects",{headers,data:{idea:"Recover a failed browser production with its existing checkpoints",channel_id:"wondernest"}});
 expect(created.status()).toBe(201);const project=await created.json();
 const root=path.resolve(process.cwd(),"../..");
 execFileSync(path.join(root,".venv/Scripts/python.exe"),[path.join(root,"tests/seed_browser_recovery.py"),project.id],{cwd:root,env:process.env,windowsHide:true});
 await request.patch(base+"/settings",{headers,data:{ai_provider:"chatgpt"}});
 await page.goto("/preview");
 await page.evaluate(id=>{localStorage.setItem("factory-project",id);localStorage.setItem("factory-channel","wondernest");},project.id);
 await page.reload();
 await expect(page.getByText("Production needs attention",{exact:true})).toBeVisible();
 await expect(page.getByText("Production interrupted: SCRIPTING",{exact:true})).toBeVisible();
 await expect(page.getByText("Codex failed; check CLI version, ChatGPT login and usage limits",{exact:true})).toBeVisible();
 const recovery=page.getByRole("region",{name:"Production text selection"});
 await expect(recovery.getByText("codex / no direct account / provider default",{exact:false})).toBeVisible();
 await expect(recovery.getByText(/New selection: chatgpt/)).toBeVisible();
 const button=recovery.getByRole("button",{name:"Use selected ChatGPT and resume",exact:true});
 await expect(button).toBeDisabled();
 await recovery.getByRole("checkbox").check();
 await button.click();
 await expect(page.getByText("Text selection applied and production resumed; completed checkpoints retained",{exact:true})).toBeVisible();
 const detail=await (await request.get(base+`/projects/${project.id}`)).json();
 expect(detail.jobs).toHaveLength(1);expect(detail.jobs[0].state).toBe("DRAFT");expect(detail.jobs[0].error).toBeNull();
 expect(detail.jobs[0].checkpoint._ai_selection.provider).toBe("chatgpt");
 expect(detail.jobs[0].checkpoint.creative_director.summary).toBe("Retained browser-test checkpoint");
 expect(detail.artifacts).toHaveLength(0);
});
