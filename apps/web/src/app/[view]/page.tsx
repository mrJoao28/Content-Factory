import { Studio } from "@/components/studio";
export default async function Page({params}:{params:Promise<{view:string}>}) { const {view}=await params;return <Studio initialView={view}/>; }
