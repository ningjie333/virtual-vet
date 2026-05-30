export interface Animal {
  species: string;
  breed: string;
  name: string;
  age: string;
  weight_kg: number;
  sex: string;
}

export interface Case {
  id: string;
  title: string;
  difficulty: number;
  difficulty_label: string;
  animal: Animal;
  chief_complaint: string;
  history: string;
  disease: string;
  time_limit_actions: number;
  starting_hints: string[];
}

export interface Vitals {
  HR_bpm: number;
  MAP_mmHg: number;
  SpO2: number;
  RR: number;
  Temp: number;
  GFR: number;
  pH: number;
  game_time?: string;
  is_night?: boolean;
}

export interface ResultEntry {
  param: string;
  value: number | string;
  unit: string;
  normal_range: string;
  flag: string;
}

export interface Report {
  name: string;
  test_type: string;
  results: ResultEntry[] | string[];
  summary: string;
  timestamp_s?: number;
  mental_status?: string;
}

export interface GameState {
  phase: string;
  time_elapsed_min: number;
  time_budget_min: number;
  time_remaining_min: number;
  medical_phase: string;
  death_timer: number | null;
  game_time?: string;
  is_night?: boolean;
}

export interface DiagnosisMatch {
  disease: string;
  confidence: number;
  matched_clues: string[];
  missed_clues: string[];
  matched_count: number;
  total_clues: number;
}

export interface TreatmentResult {
  success: boolean;
  correct: boolean;
  actual_disease: string;
  chosen_disease: string;
  phase: string;
  message: string;
}

export interface GameOverData {
  reason: string;
  actual_disease: string;
  score?: { total: number; grade: string; time_used: number };
}

export interface DrugEntry {
  drug_name: string;
  dose_mg_kg?: number;
  volume_ml?: number;
}

export interface AdministerDrugResponse {
  success: boolean;
  phase: string;
  medical_phase: string;
  time_elapsed_min: number;
  time_budget_min: number;
  time_remaining_min: number;
  death_timer: number | null;
  vitals: Vitals;
  game_log: string[];
  error?: string;
  pending_reports?: number;
  new_reports?: Report[];
  game_time?: string;
  is_night?: boolean;
  time_cost_min?: number;
}

export interface ApiResponse<T = unknown> {
  success?: boolean;
  error?: string;
  data?: T;
}

// ── 调试器类型 ──────────────────────────────────────────────────────────────

export interface BreedInfo {
  display: string;
  weight_kg: { min: number; max: number; default: number };
  size_category: string;
}

export interface SpeciesBreeds {
  [breed: string]: BreedInfo;
}

export interface SpeciesData {
  [species: string]: SpeciesBreeds;
}

export interface DebugParamEntry {
  value: number;
  unit: string;
  label_zh: string;
}

export interface DebugOrganParams {
  [param: string]: DebugParamEntry;
}

export interface DebugParamsResponse {
  input: {
    species: string;
    breed: string;
    age_days: number;
    weight_kg: number;
  };
  lifecycle: {
    phase: string;
    age_days: number;
    organ_function: Record<string, number>;
  };
  organs: {
    [organ: string]: DebugOrganParams;
  };
  summary: {
    total: number;
    organs: number;
  };
}
