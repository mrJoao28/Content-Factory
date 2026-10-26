import { defineConfig } from "@playwright/test";
// npm run test:e2e starts isolated test-owned servers through scripts/browser-test.cjs.
export default defineConfig({testDir:"./e2e",fullyParallel:false,workers:1,timeout:60000,
 use:{baseURL:"http://127.0.0.1:3001",headless:true,viewport:{width:1440,height:1000},trace:"retain-on-failure"}});
