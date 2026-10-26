export interface Project { id: string; channel_id: string; series_id: string | null; title: string; idea: string; status: string; target_duration: number; content_type: string; platform: string; revision: number; approved_hash: string | null; created_at: string; script: Record<string, unknown>; storyboard: { scenes?: Scene[] }; metadata: Record<string, unknown>; narration: Record<string, unknown>; artifacts?: Artifact[]; jobs?: Job[]; publications?: Publication[] }
export interface Scene { duration: number; background: string; narration: string; layers: unknown[] }
export interface Artifact { id: string; revision: number; sha256: string; probe: Record<string, unknown>; render_seconds: number }
export interface Job { id: string; revision: number; project_id: string; state: string; error: string | null; attempts: number; checkpoint: Record<string, unknown> }
export interface Series { id: string; channel_id: string; name: string; style: Record<string, unknown> }
export interface Character { id: string; series_id: string | null; name: string; description: string; expressions: Record<string, string> }
export interface Asset { id: string; name: string; kind: string; license: string }
export interface Log { id: number; project_id: string | null; stage: string; level: string; message: string; created_at: string }
export interface Publication { id: string; platform: string; status: string; url: string }
export interface CalendarItem { id: string; project_id: string; scheduled_at: string; timezone: string; mode: string; status: string }
export interface Connection { platform: string; status: string; scopes: string[] }
export type Diagnostic = Record<string, { state: string; instructions?: string; note?: string }>;
