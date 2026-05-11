<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch, nextTick } from "vue";
import type { Case, Vitals, Report } from "./types";
import { api } from "./api";
import CaseSelect from "./components/CaseSelect.vue";
import PatientCard from "./components/PatientCard.vue";
import ExamGrid from "./components/ExamGrid.vue";
import ReportList from "./components/ReportList.vue";
import DiagnosisPanel from "./components/DiagnosisPanel.vue";
import VitalCard from "./components/VitalCard.vue";
import GameLog from "./components/GameLog.vue";
import GameOverOverlay from "./components/GameOverOverlay.vue";

// ── State ──
const phase = ref<"select" | "game" | "done">("select");
const tab = ref<"exam" | "report" | "diag">("exam");
const sessionId = ref("");
const caseData = ref<Case | null>(null);
const cases = ref<Case[]>([]);
const examinations = ref<Record<string, { name: string; category: string; tier: number; time_cost_min: number; description: string }>>({});
const treatments = ref<Record<string, { name: string; description: string; correct_for: string | null }>>({});
const drugs = ref<Record<string, { name: string; half_life_h: number; description: string }>>({});
const examsDone = reactive(new Set<string>());
const reports = ref<Report[]>([]);
const vitals = reactive<Vitals>({ HR_bpm: 0, MAP_mmHg: 0, SpO2: 0, RR: 0, Temp: 0, GFR: 0, pH: 0 });
const timeElapsedMin = ref(0);
const timeBudgetMin = ref(90);
const timeRemainingMin = ref(90);
const medicalPhase = ref("stable");
const deathTimer = ref<number | null>(null);
const loading = ref(false);
const hint = ref("");
const hintClass = ref("");
const gameLog = ref<string[]>([]);
const gameOverData = ref<{ reason: string; actual_disease: string; score?: { total: number; grade: string; time_used: number } }>({ reason: "", actual_disease: "" });
const isNight = ref(false);
const gameTime = ref("08:00");

// ── 疾病名映射 ──
const diseaseNameMap: Record<string, string> = {
  pneumonia: "肺炎",
  acute_renal_failure: "急性肾衰竭",
  dilated_cardiomyopathy: "扩张型心肌病",
  phosphorus_poisoning: "磷化锌/磷化铝灭鼠药中毒",
  gastric_dilatation_volvulus: "胃扩张扭转",
  immune_mediated_hemolytic_anemia: "免疫介导性溶血性贫血",
  urinary_obstruction: "尿道梗阻",
  diabetic_ketoacidosis: "糖尿病酮症酸中毒",
  pericardial_effusion: "心包积液/心脏填塞",
  disseminated_intravascular_coagulation: "弥散性血管内凝血",
};

// ── Computed ──
const phaseClass = computed(() => "phase-" + medicalPhase.value);
const phaseLabel = computed(() => ({
  stable: "病情: 稳定",
  worsening: "病情: 恶化中",
  critical: "病情: 危重",
  moribund: "病情: 濒死",
}[medicalPhase.value] || "病情: —"));
const won = computed(() => phase.value === "done" && gameOverData.value.score !== undefined && gameOverData.value.score.total > 0);
const actualDiseaseName = computed(() => diseaseNameMap[gameOverData.value.actual_disease] || gameOverData.value.actual_disease);

// ── 时间显示 ──
const timePercent = computed(() => {
  if (timeBudgetMin.value <= 0) return 0;
  return Math.min(100, (timeElapsedMin.value / timeBudgetMin.value) * 100);
});
const timeBarClass = computed(() => {
  const pct = timePercent.value;
  if (pct >= 80) return "danger";
  if (pct >= 60) return "warn";
  return "ok";
});

// ── Helpers ──
function updateFrom(d: Record<string, unknown>) {
  if (d.vitals) Object.assign(vitals, d.vitals);
  if (d.time_elapsed_min !== undefined) timeElapsedMin.value = d.time_elapsed_min as number;
  if (d.time_budget_min !== undefined) timeBudgetMin.value = d.time_budget_min as number;
  if (d.time_remaining_min !== undefined) timeRemainingMin.value = d.time_remaining_min as number;
  if (d.medical_phase) medicalPhase.value = d.medical_phase as string;
  if (d.death_timer !== undefined) deathTimer.value = d.death_timer as number | null;
  if (d.game_log) gameLog.value = d.game_log as string[];
  if (d.game_over) {
    gameOverData.value = d.game_over as typeof gameOverData.value;
    phase.value = "done";
  }
  if (d.game_time !== undefined) gameTime.value = d.game_time as string;
  if (d.is_night !== undefined) isNight.value = d.is_night as boolean;
  if (d.new_reports && Array.isArray(d.new_reports)) {
    for (const r of d.new_reports) {
      if (!reports.value.find((x) => x.test_type === (r as Report).test_type && x.summary === (r as Report).summary)) {
        reports.value.push(r as Report);
      }
    }
  }
}

// ── Night mode body class ──
watch(isNight, (night) => {
  nextTick(() => {
    document.body.classList.toggle("night-mode", night);
  });
}, { immediate: true });

// ── Lifecycle ──
onMounted(async () => {
  const [c, e, t, d] = await Promise.all([
    api.getCases(), api.getExaminations(), api.getTreatments(), api.getDrugs(),
  ]);
  cases.value = c;
  examinations.value = e;
  treatments.value = t;
  drugs.value = d;
});

// ── Actions ──
async function startGame(caseId: string) {
  const d = await api.newGame(caseId);
  sessionId.value = d.session_id;
  caseData.value = d.case;
  phase.value = "game";
  Object.assign(vitals, d.vitals);
  timeElapsedMin.value = 0;
  timeBudgetMin.value = d.time_budget_min || 90;
  timeRemainingMin.value = timeBudgetMin.value;
  medicalPhase.value = d.game_state?.medical_phase || "stable";
  deathTimer.value = null;
  reports.value = [];
  examsDone.clear();
  gameLog.value = [];
  hint.value = "";
  tab.value = "exam";
  gameTime.value = d.game_time || "08:00";
  isNight.value = d.is_night || false;
}

async function doExam(testType: string) {
  if (examsDone.has(testType) || loading.value) return;
  loading.value = true;
  try {
    const d = await api.examine(sessionId.value, testType);
    if (!d.success) {
      alert(d.error || "检查失败");
      return;
    }
    if (d.report) reports.value.push(d.report);
    examsDone.add(testType);
    updateFrom(d as unknown as Record<string, unknown>);
    tab.value = "report";
    diagRefreshTrigger.value++;
  } finally {
    loading.value = false;
  }
}

async function doWait() {
  if (loading.value || phase.value === "done") return;
  loading.value = true;
  try {
    const d = await api.wait(sessionId.value);
    updateFrom(d as unknown as Record<string, unknown>);
  } finally {
    loading.value = false;
  }
}

async function submitDiagnosis() {
  if (!diagnosisInput.value || loading.value) return;
  loading.value = true;
  try {
    const d = await api.diagnose(sessionId.value, diagnosisInput.value);
    if (!d.success) {
      alert("提交失败");
      return;
    }
    updateFrom(d as unknown as Record<string, unknown>);
    if (d.treatment_result && !d.treatment_result.correct) {
      hint.value = d.treatment_result.message;
      hintClass.value = "err";
      tab.value = "diag";
    }
  } finally {
    loading.value = false;
  }
}

const diagnosisInput = ref("");
const diagRefreshTrigger = ref(0);

async function doSupportiveCare() {
  if (loading.value || phase.value === "done") return;
  loading.value = true;
  try {
    const d = await api.diagnose(sessionId.value, "supportive_care");
    if (!d.success) {
      alert("操作失败");
      return;
    }
    updateFrom(d as unknown as Record<string, unknown>);
    if (d.treatment_result) {
      hint.value = d.treatment_result.message;
      hintClass.value = "info";
      tab.value = "diag";
    }
  } finally {
    loading.value = false;
  }
}

async function doAdministerDrug(drugName: string, doseMgKg: number | null, volumeMl: number | null) {
  if (loading.value || phase.value === "done") return;
  loading.value = true;
  try {
    const drug: Record<string, string | number> = { drug_name: drugName };
    if (volumeMl !== null && volumeMl > 0) {
      drug.volume_ml = volumeMl;
    } else if (doseMgKg !== null && doseMgKg > 0) {
      drug.dose_mg_kg = doseMgKg;
    }
    const d = await api.administerDrug(sessionId.value, drug as { drug_name: string; dose_mg_kg?: number; volume_ml?: number });
    if (!d.success) {
      hint.value = d.error || "给药失败";
      hintClass.value = "err";
      return;
    }
    updateFrom(d as unknown as Record<string, unknown>);
    hint.value = `已给药：${drugName}`;
    hintClass.value = "info";
  } finally {
    loading.value = false;
  }
}

function getDefaultDose(drugName: string): number {
  const doses: Record<string, number> = {
    pimobendan: 0.25,
    furosemide: 1.0,
    epinephrine: 0.02,
  };
  return doses[drugName] || 1.0;
}

async function loadHint() {
  const d = await api.getHint(sessionId.value);
  hint.value = d.hint || "暂无提示";
  hintClass.value = "";
}

function goBack() {
  phase.value = "select";
  caseData.value = null;
  reports.value = [];
  examsDone.clear();
  gameLog.value = [];
  hint.value = "";
  diagnosisInput.value = "";
}

function restart() {
  phase.value = "select";
  caseData.value = null;
  reports.value = [];
  examsDone.clear();
  gameLog.value = [];
  hint.value = "";
  diagnosisInput.value = "";
}
</script>

<template>
  <div class="game-app">
    <!-- ── Top Bar ── -->
    <div class="top-bar">
      <div class="top-left">
        <span class="top-logo">🐾 Virtual Vet · 兽医诊断游戏</span>
        <button v-if="phase !== 'select'" class="btn-back" @click="goBack" title="返回病例选择">
          ← 返回
        </button>
      </div>
      <div class="top-right" v-if="phase !== 'select'">
        <!-- 时间预算条 -->
        <div class="time-budget-container">
          <div class="time-budget-label">
            <span :class="['clock-display', { night: isNight }]">{{ isNight ? '🌙' : '🕐' }} {{ gameTime }}</span>
            <span class="time-remaining" :class="timeBarClass">{{ timeRemainingMin }} min 剩余</span>
          </div>
          <div class="time-budget-bar">
            <div class="time-budget-fill" :class="timeBarClass" :style="{ width: timePercent + '%' }"></div>
          </div>
        </div>
        <span v-if="isNight" class="badge badge-night">夜间模式</span>
        <span :class="['badge', phaseClass]">{{ phaseLabel }}</span>
        <span class="death-timer" v-if="deathTimer !== null">⚠ 濒死倒计时: {{ deathTimer }}</span>
      </div>
    </div>

    <!-- ── Left: Patient Info ── -->
    <div class="left-panel">
      <template v-if="!caseData">
        <div style="color: var(--text-muted); font-size: 0.78rem; text-align: center; padding: 40px 10px">
          请先选择一个病例开始诊疗
        </div>
      </template>
      <template v-else>
        <PatientCard :case-data="caseData" />
      </template>
    </div>

    <!-- ── Center: Main ── -->
    <div class="center-panel">
      <!-- Case Selection -->
      <CaseSelect v-if="phase === 'select'" :cases="cases" @select="startGame" />

      <!-- Game Phase -->
      <template v-else>
        <div style="display: flex; flex-direction: column; gap: 10px; flex: 1">
          <!-- Tabs -->
          <div class="tab-row">
            <button :class="['tab', { active: tab === 'exam' }]" @click="tab = 'exam'">🔬 开具检查</button>
            <button :class="['tab', { active: tab === 'report' }]" @click="tab = 'report'">
              📋 检查报告
              <span v-if="reports.length" style="color: var(--cyan); margin-left: 4px">({{ reports.length }})</span>
            </button>
            <button :class="['tab', { active: tab === 'diag' }]" @click="tab = 'diag'">🩺 诊断与治疗</button>
          </div>

          <!-- Exam Tab -->
          <ExamGrid
            v-if="tab === 'exam'"
            :examinations="examinations"
            :exams-done="examsDone"
            :reports="reports"
            :loading="loading"
            :time-remaining-min="timeRemainingMin"
            @exam="doExam"
          />

          <!-- Report Tab -->
          <ReportList v-if="tab === 'report'" :reports="reports" />

          <!-- Diagnosis Tab -->
          <DiagnosisPanel
            v-if="tab === 'diag'"
            v-model="diagnosisInput"
            :hint="hint"
            :hint-class="hintClass"
            :treatments="treatments"
            :session-id="sessionId"
            :refresh-trigger="diagRefreshTrigger"
            @submit="submitDiagnosis"
            @hint="loadHint"
            @supportive-care="doSupportiveCare"
          />

          <!-- Emergency Drug Panel (always visible in game) -->
          <div v-if="tab === 'diag' && Object.keys(drugs).length > 0" class="drug-panel">
            <div class="panel-ttl">💊 紧急给药</div>
            <div class="drug-grid">
              <button
                v-for="(info, key) in drugs"
                :key="key"
                class="btn btn-drug"
                :disabled="loading || phase === 'done'"
                @click="info.half_life_h > 10
                  ? doAdministerDrug(key, null, 200)
                  : doAdministerDrug(key, getDefaultDose(key), null)"
                :title="info.description"
              >
                <span class="drug-name">{{ info.name }}</span>
                <span class="drug-info">{{ info.description }}</span>
                <span class="drug-half">t½: {{ info.half_life_h }}h</span>
              </button>
            </div>
          </div>

          <!-- Game Log -->
          <GameLog :entries="gameLog" />
        </div>
      </template>
    </div>

    <!-- ── Right: Vitals ── -->
    <div class="right-panel">
      <div class="panel-ttl">生命体征</div>
      <template v-if="phase === 'select'">
        <div style="color: var(--text-muted); font-size: 0.75rem; text-align: center; padding: 30px 8px">
          开始游戏后显示
        </div>
      </template>
      <template v-else>
        <VitalCard label="心 率 HR" id="HR_bpm" unit="bpm" :warn="[60, 140]" :danger="[50, 170]" :vitals="vitals" :is-night="isNight" />
        <VitalCard label="平均动脉压 MAP" id="MAP_mmHg" unit="mmHg" :warn="[70, 120]" :danger="[55, 150]" :vitals="vitals" />
        <VitalCard label="血氧饱和度 SpO₂" id="SpO2" unit="%" :warn="[95, 100]" :danger="[85, 100]" :vitals="vitals" />
        <VitalCard label="呼吸频率 RR" id="RR" unit="/min" :warn="[12, 30]" :danger="[8, 40]" :vitals="vitals" />
        <VitalCard label="肾小球滤过率 GFR" id="GFR" unit="mL/min" :warn="[50, 120]" :danger="[20, 200]" :vitals="vitals" />
        <VitalCard label="动脉血 pH" id="pH" unit="" :warn="[7.35, 7.45]" :danger="[7.2, 7.55]" :vitals="vitals" />
        <div style="margin-top: 8px">
          <button
            class="btn btn-ghost"
            style="width: 100%; font-size: 0.75rem"
            @click="doWait"
            :disabled="phase === 'done'"
          >
            ⏳ 等待观察（10 分钟）
          </button>
        </div>
      </template>
    </div>
  </div>

  <!-- Game Over Overlay -->
  <GameOverOverlay
    v-if="phase === 'done'"
    :data="gameOverData"
    :won="won"
    :disease-name="actualDiseaseName"
    @restart="restart"
  />
</template>

<style scoped>
.top-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.btn-back {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  padding: 4px 10px;
  border-radius: 6px;
  font-family: var(--mono);
  font-size: 0.65rem;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-back:hover {
  border-color: var(--cyan);
  color: var(--cyan);
}

/* ── Time Budget Bar ── */
.time-budget-container {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 160px;
}
.time-budget-label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.time-remaining {
  font-family: var(--mono);
  font-size: 0.65rem;
  font-weight: 600;
}
.time-remaining.ok { color: #4caf50; }
.time-remaining.warn { color: #ff9800; }
.time-remaining.danger { color: #f44336; }
.time-budget-bar {
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
}
.time-budget-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease, background 0.3s ease;
}
.time-budget-fill.ok { background: #4caf50; }
.time-budget-fill.warn { background: #ff9800; }
.time-budget-fill.danger { background: #f44336; }

/* ── Drug Panel ── */
.drug-panel {
  margin-top: 10px;
  background: rgba(255, 152, 0, 0.04);
  border: 1px solid rgba(255, 152, 0, 0.15);
  border-radius: 8px;
  padding: 10px 12px;
}
.drug-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.btn-drug {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 10px;
  background: rgba(255, 152, 0, 0.06);
  border: 1px solid rgba(255, 152, 0, 0.2);
  border-radius: 6px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.btn-drug:hover:not(:disabled) {
  background: rgba(255, 152, 0, 0.12);
  border-color: rgba(255, 152, 0, 0.4);
}
.btn-drug:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.drug-name {
  font-weight: 600;
  font-size: 0.72rem;
}
.drug-info {
  font-size: 0.58rem;
  color: var(--text-muted);
  line-height: 1.3;
}
.drug-half {
  font-family: var(--mono);
  font-size: 0.55rem;
  color: var(--text-dim);
}
</style>
