export type Job = {
  id: string; name: string; status: "queued" | "processing" | "done" | "failed";
  model: "quality" | "fast"; refine: boolean; width: number; height: number;
  created_at: string; error: string | null; original_url: string; result_url: string | null;
  progress: number; stage: string; pipeline: string;
  eye_sharpen: boolean; face_clean: boolean; face_sharpen: boolean; face_spots: boolean;
  face_strength: number; face_report: { faces?: number; spots?: number; changed_pixels?: number; message?: string };
};
export type Health = { status: string; engine: string; device: "cpu" | "cuda"; pipeline: string; resolution: number };
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "İstek tamamlanamadı. Uygulamanın çalıştığını kontrol edin.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function downloadUrl(job: Job, background: string, format: string, preset: string) {
  return `/api/jobs/${job.id}/download?${new URLSearchParams({ background, format, preset })}`;
}
