import type {
  Case,
  DiagnosisResponse,
  DrugEntry,
  AdministerDrugResponse,
  DiseaseReference,
  ExamineResponse,
  DiagnoseResponse,
  WaitResponse,
  GameStateResponse,
  NewGameResponse,
} from "./types";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

const BASE = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || "/api");

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${BASE}${path}`, opts);
  return r.json();
}

export const api = {
  getCases: (): Promise<Case[]> => request("GET", "/cases"),

  getExaminations: () => request<Record<string, { name: string; category: string; tier: number; time_cost_min: number; description: string }>>("GET", "/examinations"),

  getTreatments: () => request<Record<string, { name: string; description: string; correct_for: string | null }>>("GET", "/treatments"),

  newGame: (caseId: string): Promise<NewGameResponse> =>
    request("POST", "/new-game", { case_id: caseId }),

  examine: (sessionId: string, testType: string): Promise<ExamineResponse> =>
    request("POST", "/examine", { session_id: sessionId, test_type: testType }),

  diagnose: (sessionId: string, diagnosis: string): Promise<DiagnoseResponse> =>
    request("POST", "/diagnose", { session_id: sessionId, diagnosis }),

  wait: (sessionId: string): Promise<WaitResponse> =>
    request("POST", "/wait", { session_id: sessionId }),

  getGameState: (sessionId: string): Promise<GameStateResponse> =>
    request("GET", `/game-state?session_id=${encodeURIComponent(sessionId)}`),

  getHint: (sessionId: string): Promise<{ hint: string }> =>
    request("GET", `/hint?session_id=${encodeURIComponent(sessionId)}`),

  getDiagnosis: (sessionId: string): Promise<DiagnosisResponse> =>
    request("GET", `/diagnosis?session_id=${encodeURIComponent(sessionId)}`),

  getDiseaseReferences: (diseaseName: string): Promise<DiseaseReference> =>
    request("GET", `/disease-references/${encodeURIComponent(diseaseName)}`),

  getDrugs: (): Promise<Record<string, { name: string; half_life_h: number; description: string }>> =>
    request("GET", "/drugs"),

  administerDrug: (sessionId: string, drug: DrugEntry): Promise<AdministerDrugResponse> =>
    request("POST", "/administer-drug", {
      session_id: sessionId,
      drug_name: drug.drug_name,
      ...(drug.volume_ml !== undefined ? { volume_ml: drug.volume_ml } : { dose_mg_kg: drug.dose_mg_kg }),
    }),
};

// ── 调试器 API ──────────────────────────────────────────────────────────────

export const debugApi = {
  getSpecies: (): Promise<Record<string, Record<string, { display: string; weight_kg: { min: number; max: number; default: number }; size_category: string }>>> => request("GET", "/debug/species"),

  getParams: (params: { species: string; breed: string; age_days: number; weight_kg?: number }): Promise<Record<string, unknown>> => request("POST", "/debug/params", params),

  getDiseases: (): Promise<{ id: string; display: string; severities: string[] }[]> => request("GET", "/debug/diseases"),

  getDiseaseParams: (params: { species: string; weight_kg: number; age_days?: number; lifecycle_mode?: string; disease: string; severity: string; warmup_minutes: number }): Promise<{
    input: Record<string, unknown>;
    healthy: Record<string, number>;
    disease: Record<string, number>;
  }> => request("POST", "/debug/disease-params", params),
};
