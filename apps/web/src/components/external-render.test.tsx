import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import type { Project } from "@/lib/types";
import { ExternalRender } from "./external-render";

describe("external render state",()=>{
 it("shows external waiting without invented progress or automatic approval",()=>{
  const project={id:"fixture",revision:1,visual_config:{engine:"blender_3d",execution_location:"colab"},jobs:[{revision:1,state:"WAITING_FOR_EXTERNAL_RENDER",checkpoint:{}}]} as Project;
  const html=renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><ExternalRender project={project} busy={false} act={()=>{}}/></QueryClientProvider>);
  expect(html).toContain("Waiting for external execution/import");
  expect(html).toContain("no live Colab progress");
  expect(html).toContain("Export package");
  expect(html).toContain("Import Colab result");
  expect(html).toContain("Return to local render");
  expect(html).not.toContain("Approve video");
 });
});
