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
  action_count?: number;
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
  action_count: number;
  elapsed_time_s: number;
  medical_phase: string;
  death_timer: number | null;
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
  score?: { total: number; grade: string; actions_used: number };
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
  action_count: number;
  elapsed_time_s: number;
  death_timer: number | null;
  vitals: Vitals;
  game_log: string[];
  error?: string;
}

export interface ApiResponse<T = unknown> {
  success?: boolean;
  error?: string;
  data?: T;
}
