export interface TopazOutput {
  source: string;
  group: string;
  room: number;
  label: string;
  originalUrl: string;
  outputUrl: string;
  scale: 4 | 6;
  crispUrl?: string;
  cutoutUrl?: string;
  previousUrl?: string;
  processing?: 'matting' | 'opaque' | 'derived' | 'manual';
  previousScale?: 4 | 6;
  width: number;
  height: number;
}

export interface TopazSnapshot {
  prepared: number;
  ready: number;
  matched: number;
  page: number;
  pages: number;
  groups: { id: string; count: number }[];
  rooms: { room: number; ready: number; prepared: number }[];
  outputs: TopazOutput[];
  cutouts?: { ready: number; total: number; state: string; guybrush: number; wally: number; cannon: number };
  sceneBatch?: {
    state: string; current: string | null; creditCap: number; submitted: number;
    previousCrisp: { total: number; ready: number };
    scenes: { id: string; room: number; name: string; total: number; ready: number; preserved: number; smallPilots: number; minimumCredits: number }[];
  };
  progress: {
    state: string;
    current_source?: string;
    updated_at: number;
    run_completed: number;
    run_estimated_credits: number;
    run_credit_cap: number;
    downloads_pending?: number;
  } | null;
}
