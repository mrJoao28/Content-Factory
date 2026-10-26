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
