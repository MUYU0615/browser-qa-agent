export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';

export type RunEvent = {
  at: string;
  node: string;
  message: string;
};

export type Issue = {
  severity: string;
  kind: string;
  message: string;
  reproduction_steps?: string[] | string;
};

export type LlmCall = {
  at: string;
  node: string;
  purpose: string;
  called_model: boolean;
  model: string;
  base_url: string;
  prompt: string;
  raw_output: string;
  parsed_output: unknown;
  fallback_reason?: string;
};

export type Attempt = {
  attempt: number;
  phase: string;
  test_steps: Array<Record<string, unknown>>;
  execution_results: Array<{
    ok: boolean;
    description?: string;
    action?: string;
    error?: string | null;
    screenshot?: string;
  }>;
  console_errors: Array<Record<string, unknown>>;
  network_errors: Array<Record<string, unknown>>;
  screenshots: string[];
};

export type Run = {
  id: string;
  url: string;
  status: RunStatus;
  current_node: string;
  created_at: string;
  updated_at: string;
  events: RunEvent[];
  llm_calls: LlmCall[];
  attempts: Attempt[];
  screenshots: string[];
  issues: Issue[];
  report_path?: string | null;
  error?: string | null;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export async function createRun(url: string): Promise<Run> {
  const response = await fetch(`${API_BASE}/api/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function getRun(runId: string): Promise<Run> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function getReport(runId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/report`);
  if (!response.ok) {
    return '';
  }
  return response.text();
}
