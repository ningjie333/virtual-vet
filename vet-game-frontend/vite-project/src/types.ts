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
  time_used?: number;
  game_time?: string;
  is_night?: boolean;
}

export interface ApStressState {
  ap: number;
  max_ap: number;
  stress: number;
  pending_reports: number;
  ap_cost?: number;
  combo_bonus?: string | null;
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
  time_used: number;
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
  time_used: number;
  death_timer: number | null;
  vitals: Vitals;
  game_log: string[];
  error?: string;
  ap?: number;
  max_ap?: number;
  stress?: number;
  pending_reports?: number;
  new_reports?: Report[];
  game_time?: string;
  is_night?: boolean;
}

export interface ApiResponse<T = unknown> {
  success?: boolean;
  error?: string;
  data?: T;
}
