export interface Project { visual_config?: Partial<import("@/components/visual-production").VisualChoice>; id: string; channel_id: string; series_id: string | null; title: string; idea: string; status: string; target_duration: number; content_type: string; platform: string; revision: number; approved_hash: string | null; created_at: string; script: Record<string, unknown>; storyboard: { scenes?: Scene[] }; metadata: Record<string, unknown>; narration: Record<string, unknown>; artifacts?: Artifact[]; jobs?: Job[]; publications?: Publication[] }
export interface Scene { duration: number; background: string; narration: string; layers?: unknown[]; characters?: unknown[] }
export interface Artifact { id: string; revision: number; sha256: string; probe: Record<string, unknown>; render_seconds: number }
export interface Job { owner?:string|null;lease_until?:string|null; id: string; revision: number; project_id: string; state: string; error: string | null; attempts: number; checkpoint: Record<string, unknown>; diagnostic?: {selection: {provider?:string;account_id?:string|null;model?:string|null}|null; selection_source:string; stage:string|null; code:string|null; failure_provider?:string|null; response?: {http_status:number;content_type:string;request_id:string|null;format:string;error_code:string|null;message:string|null}|null; global:{provider:string;source:string}; next_action:string; completed_steps:string[]} }
export interface Series { id: string; channel_id: string; name: string; style: Record<string, unknown> }
export interface Character { id: string; series_id: string | null; name: string; description: string; expressions: Record<string, string> }
export interface Asset { id: string; name: string; kind: string; license: string }
export interface Log { id: number; project_id: string | null; stage: string; level: string; message: string; created_at: string }
export interface Publication { id: string; platform: string; status: string; url: string }
export interface CalendarItem { id: string; project_id: string; scheduled_at: string; timezone: string; mode: string; status: string }
export interface Connection { platform: string; status: string; scopes: string[] }
export type Diagnostic = Record<string, { state: string; instructions?: string; note?: string }>;
