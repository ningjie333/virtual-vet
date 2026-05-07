import type { Case, Report, Vitals, GameState, TreatmentResult, GameOverData, DiagnosisMatch, DrugEntry, AdministerDrugResponse } from "./types";

const BASE = "/api";

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

  getExaminations: () => request<Record<string, { name: string; name_en: string; category: string; tier: number; cost: number; description: string }>>("GET", "/examinations"),

  getTreatments: () => request<Record<string, { name: string; description: string; correct_for: string | null }>>("GET", "/treatments"),

  newGame: (caseId: string): Promise<{ session_id: string; case: Case; game_state: GameState; vitals: Vitals; game_time: string; is_night: boolean }> =>
    request("POST", "/new-game", { case_id: caseId }),

  examine: (sessionId: string, testType: string): Promise<{
    success: boolean;
    phase: string;
    medical_phase: string;
    time_used: number;
    death_timer: number | null;
    report: Report;
    vitals: Vitals;
    game_log: string[];
    game_over?: GameOverData;
  }> => request("POST", "/examine", { session_id: sessionId, test_type: testType }),

  diagnose: (sessionId: string, diagnosis: string): Promise<{
    success: boolean;
    phase: string;
    medical_phase: string;
    time_used: number;
    death_timer: number | null;
    treatment_result: TreatmentResult;
    vitals: Vitals;
    game_log: string[];
    game_over?: GameOverData;
  }> => request("POST", "/diagnose", { session_id: sessionId, diagnosis }),

  wait: (sessionId: string): Promise<{
    success: boolean;
    phase: string;
    medical_phase: string;
    time_used: number;
    death_timer: number | null;
    vitals: Vitals;
    game_log: string[];
    game_over?: GameOverData;
  }> => request("POST", "/wait", { session_id: sessionId }),

  getGameState: (sessionId: string): Promise<{
    phase: string;
    medical_phase: string;
    time_used: number;
    death_timer: number | null;
    vitals: Vitals;
    reports_count: number;
    game_log: string[];
  }> => request("GET", "/game-state", { session_id: sessionId }),

  getHint: (sessionId: string): Promise<{ hint: string }> =>
    request("GET", `/hint?session_id=${sessionId}`),

  getDiagnosis: (sessionId: string): Promise<{
    matches: DiagnosisMatch[];
    suggested_tests: string[];
  }> => request("GET", `/diagnosis?session_id=${sessionId}`),

  getDrugs: (): Promise<Record<string, { name: string; half_life_h: number; description: string }>> =>
    request("GET", "/drugs"),

  administerDrug: (sessionId: string, drug: DrugEntry): Promise<AdministerDrugResponse> =>
    request("POST", "/administer-drug", {
      session_id: sessionId,
      drug_name: drug.drug_name,
      ...(drug.volume_ml !== undefined ? { volume_ml: drug.volume_ml } : { dose_mg_kg: drug.dose_mg_kg }),
    }),
};
