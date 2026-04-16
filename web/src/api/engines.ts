import { apiFetch } from "./client";

export interface EngineSpec {
  name: string;
  display_name: string;
  docker_image?: string;
  api_style: string;
  default_port: number;
  formats: string[];
  modes: string[];
  default_mode: string;
  description?: string;
}

export async function listEngines(): Promise<EngineSpec[]> {
  return apiFetch<EngineSpec[]>("/api/v1/engines");
}

export interface Recommendation {
  engine: string;
  quantization?: string;
  rationale: string;
  score: number;
}

export interface RecommendationRequest {
  gpu_vram_gib?: number;
  unified_memory?: boolean;
  task?: string;
  desired_formats?: string[];
}

export async function recommend(
  req: RecommendationRequest
): Promise<Recommendation[]> {
  const params = new URLSearchParams();
  if (req.gpu_vram_gib) params.set("vram", String(req.gpu_vram_gib));
  if (req.unified_memory) params.set("unified", "true");
  if (req.task) params.set("task", req.task);
  for (const f of req.desired_formats ?? []) {
    params.append("format", f);
  }
  return apiFetch<Recommendation[]>(`/api/v1/recommend?${params.toString()}`);
}
