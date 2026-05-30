<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { debugApi } from "../api";
import type { DebugParamsResponse } from "../types";

const emit = defineEmits<{
  close: [];
}>();

// ── 状态 ──
const species = ref("canine");
const breed = ref("labrador");
const ageDays = ref(1095);
const weightKg = ref(30.0);
const loading = ref(false);
const result = ref<DebugParamsResponse | null>(null);
const activeOrgan = ref("heart");

// ── 品种数据 ──
interface BreedInfo {
  display: string;
  weight_kg: { min: number; max: number; default: number };
  size_category: string;
}
type SpeciesBreeds = Record<string, BreedInfo>;
type SpeciesData = Record<string, SpeciesBreeds>;

const speciesData = ref<SpeciesData>({});

onMounted(async () => {
  speciesData.value = await debugApi.getSpecies();
  updateWeightFromBreed();
});

// ── 计算属性 ──
const currentBreeds = computed(() => {
  return speciesData.value[species.value] || {};
});

const breedKeys = computed(() => Object.keys(currentBreeds.value));

const ageYears = computed(() => (ageDays.value / 365).toFixed(1));

const lifePhase = computed(() => {
  if (result.value?.lifecycle?.phase) {
    return result.value.lifecycle.phase;
  }
  const days = ageDays.value;
  if (days < 14) return "neonatal";
  if (days < 60) return "juvenile";
  if (days < 1095) return "young_adult";
  if (days < 2555) return "adult";
  if (days < 3650) return "senior";
  return "geriatric";
});

const lifePhaseLabel = computed(() => {
  const labels: Record<string, string> = {
    neonatal: "新生期",
    juvenile: "幼年期",
    young_adult: "青年期",
    adult: "成年期",
    senior: "老年期",
    geriatric: "高龄期",
  };
  return labels[lifePhase.value] || lifePhase.value;
});

const organTabs = computed(() => {
  if (!result.value?.organs) return [];
  return Object.keys(result.value.organs);
});

const organLabels: Record<string, string> = {
  heart: "心脏",
  lung: "肺",
  kidney: "肾",
  blood: "血液",
  fluid: "体液",
  gut: "肠道",
  liver: "肝脏",
  endocrine: "内分泌",
  neuro: "神经",
  immune: "免疫",
  coagulation: "凝血",
  lymphatic: "淋巴",
};

const organColors: Record<string, string> = {
  heart: "#EF5350",
  lung: "#4FC3F7",
  kidney: "#66BB6A",
  blood: "#EF5350",
  fluid: "#4FC3F7",
  gut: "#FFA726",
  liver: "#FFA726",
  endocrine: "#AB47BC",
  neuro: "#AB47BC",
  immune: "#66BB6A",
  coagulation: "#EF5350",
  lymphatic: "#4FC3F7",
};

// ── 方法 ──
function updateWeightFromBreed() {
  const info = currentBreeds.value[breed.value];
  if (info) {
    weightKg.value = info.weight_kg.default;
  }
}

function onSpeciesChange() {
  const keys = Object.keys(currentBreeds.value);
  breed.value = keys.includes("mixed") ? "mixed" : keys[0] || "mixed";
  updateWeightFromBreed();
}

function onBreedChange() {
  updateWeightFromBreed();
}

async function computeParams() {
  loading.value = true;
  try {
    const data = await debugApi.getParams({
      species: species.value,
      breed: breed.value,
      age_days: ageDays.value,
      weight_kg: weightKg.value,
    });
    result.value = data as unknown as DebugParamsResponse;
  } catch (e) {
    console.error("Debug params error:", e);
  } finally {
    loading.value = false;
  }
}

function resetParams() {
  species.value = "canine";
  breed.value = "labrador";
  ageDays.value = 1095;
  weightKg.value = 30.0;
  result.value = null;
  activeOrgan.value = "heart";
}

function formatValue(val: number): string {
  if (val === 0) return "0";
  if (Math.abs(val) < 0.001) return val.toExponential(2);
  if (Math.abs(val) >= 10000) return val.toExponential(2);
  return val.toFixed(2);
}

function getOrganParamCount(organ: string): number {
  return result.value?.organs?.[organ] ? Object.keys(result.value.organs[organ]).length : 0;
}
</script>

<template>
  <div class="debug-page">
    <!-- 顶部栏 -->
    <div class="debug-top-bar">
      <div class="debug-top-left">
        <span class="debug-logo">🔬 生理参数调试器</span>
      </div>
      <div class="debug-top-right">
        <button class="btn btn-ghost" @click="emit('close')">← 返回游戏</button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="debug-main">
      <!-- 左侧控制面板 -->
      <div class="debug-left-panel">
        <div class="panel-ttl">参数配置</div>

        <!-- 物种选择 -->
        <div class="debug-field">
          <label class="debug-label">物种</label>
          <div class="radio-group">
            <button
              v-for="s in Object.keys(speciesData)"
              :key="s"
              :class="['radio-btn', { active: species === s }]"
              @click="species = s; onSpeciesChange()"
            >
              {{ s === "canine" ? "🐕 犬" : s === "feline" ? "🐱 猫" : "🐴 马" }}
            </button>
          </div>
        </div>

        <!-- 品种选择 -->
        <div class="debug-field">
          <label class="debug-label">品种</label>
          <select v-model="breed" @change="onBreedChange" class="debug-select">
            <option v-for="key in breedKeys" :key="key" :value="key">
              {{ currentBreeds[key]?.display || key }}
            </option>
          </select>
        </div>

        <!-- 年龄滑块 -->
        <div class="debug-field">
          <label class="debug-label">年龄</label>
          <input
            v-model.number="ageDays"
            type="range"
            :min="0"
            :max="8000"
            :step="30"
            class="debug-slider"
          />
          <div class="debug-age-display">
            <span class="age-days">{{ ageDays }} 天</span>
            <span class="age-years">({{ ageYears }} 岁)</span>
          </div>
          <div class="debug-phase">
            <span :class="['phase-badge', lifePhase]">{{ lifePhaseLabel }}</span>
          </div>
        </div>

        <!-- 体重输入 -->
        <div class="debug-field">
          <label class="debug-label">体重 (kg)</label>
          <input
            v-model.number="weightKg"
            type="number"
            :min="0.1"
            :max="200"
            :step="0.5"
            class="debug-input"
          />
        </div>

        <!-- 操作按钮 -->
        <div class="debug-actions">
          <button class="btn btn-primary" @click="computeParams" :disabled="loading">
            {{ loading ? "计算中..." : "计算参数" }}
          </button>
          <button class="btn btn-ghost" @click="resetParams">重置</button>
        </div>

        <!-- 统计信息 -->
        <div v-if="result?.summary" class="debug-stats">
          <div class="panel-ttl">统计</div>
          <div class="stats-grid">
            <div class="stats-item">
              <span class="stats-label">器官系统</span>
              <span class="stats-value">{{ result.summary.organs }}</span>
            </div>
            <div class="stats-item">
              <span class="stats-label">总参数</span>
              <span class="stats-value">{{ result.summary.total }}</span>
            </div>
          </div>
        </div>

        <!-- 生命周期信息 -->
        <div v-if="result?.lifecycle?.phase" class="debug-lifecycle">
          <div class="panel-ttl">生命周期</div>
          <div class="lifecycle-phase">
            <span :class="['phase-badge', result.lifecycle.phase]">
              {{ lifePhaseLabel }}
            </span>
          </div>
          <div v-if="result.lifecycle.organ_function" class="organ-function">
            <div
              v-for="(val, organ) in result.lifecycle.organ_function"
              :key="organ"
              class="function-bar"
            >
              <span class="function-label">{{ organLabels[organ as string] || organ }}</span>
              <div class="function-track">
                <div
                  class="function-fill"
                  :style="{
                    width: (val * 100) + '%',
                    backgroundColor: organColors[organ as string] || '#4FC3F7'
                  }"
                ></div>
              </div>
              <span class="function-value">{{ (val * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧参数面板 -->
      <div class="debug-right-panel">
        <template v-if="result">
          <!-- 器官标签页 -->
          <div class="organ-tabs">
            <button
              v-for="organ in organTabs"
              :key="organ"
              :class="['organ-tab', { active: activeOrgan === organ }]"
              :style="{ borderColor: organColors[organ] }"
              @click="activeOrgan = organ"
            >
              {{ organLabels[organ] || organ }}
              <span class="param-count">{{ getOrganParamCount(organ) }}</span>
            </button>
          </div>

          <!-- 参数表格 -->
          <div class="param-table-container">
            <table class="param-table">
              <thead>
                <tr>
                  <th>参数</th>
                  <th>英文名</th>
                  <th>值</th>
                  <th>单位</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(info, param) in result.organs[activeOrgan]"
                  :key="param"
                  :style="{ borderLeftColor: organColors[activeOrgan] }"
                >
                  <td class="param-label">{{ info.label_zh }}</td>
                  <td class="param-key">{{ param }}</td>
                  <td class="param-value">{{ formatValue(info.value) }}</td>
                  <td class="param-unit">{{ info.unit }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- 空状态 -->
        <template v-else>
          <div class="empty-state">
            <div class="empty-icon">🔬</div>
            <div class="empty-title">生理参数调试器</div>
            <div class="empty-text">配置参数后点击"计算参数"查看结果</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 页面布局 ── */
.debug-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-void);
  color: var(--text);
}

.debug-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  padding: 0 16px;
  height: 52px;
  flex-shrink: 0;
}

.debug-top-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.debug-logo {
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--cyan);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.debug-top-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.debug-main {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 10px;
  padding: 10px;
  overflow: hidden;
}

/* ── 左侧面板 ── */
.debug-left-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.debug-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.debug-label {
  font-family: var(--mono);
  font-size: 0.62rem;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  text-transform: uppercase;
}

.radio-group {
  display: flex;
  gap: 6px;
}

.radio-btn {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.2s;
}

.radio-btn:hover {
  border-color: var(--border-hi);
  color: var(--text);
}

.radio-btn.active {
  border-color: var(--cyan);
  background: rgba(79, 195, 247, 0.1);
  color: var(--cyan);
}

.debug-select,
.debug-input {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text);
  font-size: 0.82rem;
  outline: none;
}

.debug-select:focus,
.debug-input:focus {
  border-color: var(--cyan);
}

.debug-slider {
  width: 100%;
  accent-color: var(--cyan);
  margin: 4px 0;
}

.debug-age-display {
  display: flex;
  gap: 8px;
  font-family: var(--mono);
  font-size: 0.75rem;
}

.age-days {
  color: var(--text);
  font-weight: 600;
}

.age-years {
  color: var(--text-dim);
}

.debug-phase {
  margin-top: 4px;
}

.phase-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 6px;
  font-family: var(--mono);
  font-size: 0.7rem;
  border: 1px solid;
}

.phase-badge.neonatal,
.phase-badge.juvenile {
  color: var(--org);
  border-color: rgba(255, 167, 38, 0.3);
  background: rgba(255, 167, 38, 0.06);
}

.phase-badge.young_adult,
.phase-badge.adult {
  color: var(--grn);
  border-color: rgba(102, 187, 106, 0.3);
  background: rgba(102, 187, 106, 0.06);
}

.phase-badge.senior,
.phase-badge.geriatric {
  color: var(--red);
  border-color: rgba(239, 83, 80, 0.3);
  background: rgba(239, 83, 80, 0.06);
}

.debug-actions {
  display: flex;
  gap: 8px;
}

.debug-stats,
.debug-lifecycle {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.stats-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stats-label {
  font-family: var(--mono);
  font-size: 0.58rem;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.stats-value {
  font-family: var(--mono);
  font-size: 1.1rem;
  font-weight: 600;
  color: #e8f4ff;
}

.lifecycle-phase {
  margin-bottom: 12px;
}

.organ-function {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.function-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.function-label {
  width: 48px;
  font-family: var(--mono);
  font-size: 0.62rem;
  color: var(--text-muted);
  text-align: right;
}

.function-track {
  flex: 1;
  height: 6px;
  background: var(--bg-deep);
  border-radius: 3px;
  overflow: hidden;
}

.function-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.function-value {
  width: 36px;
  font-family: var(--mono);
  font-size: 0.62rem;
  text-align: right;
  color: var(--text-dim);
}

/* ── 右侧面板 ── */
.debug-right-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.organ-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
}

.organ-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 16px;
  border: 1px solid transparent;
  border-bottom: 3px solid transparent;
  border-radius: 7px 7px 0 0;
  background: transparent;
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 0.7rem;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.organ-tab:hover {
  color: var(--text);
  background: var(--bg-card);
}

.organ-tab.active {
  color: var(--cyan);
  background: rgba(79, 195, 247, 0.1);
  border-color: var(--border);
  border-bottom-color: var(--cyan);
}

.param-count {
  font-size: 0.62rem;
  color: var(--text-muted);
}

.param-table-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.param-table {
  width: 100%;
  border-collapse: collapse;
}

.param-table th {
  font-family: var(--mono);
  font-size: 0.62rem;
  color: var(--text-muted);
  text-align: left;
  padding: 3px 7px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg-panel);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.param-table td {
  font-family: var(--mono);
  font-size: 0.72rem;
  padding: 6px 7px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.param-table tr {
  border-left: 3px solid transparent;
  transition: background 0.1s;
}

.param-table tr:hover {
  background: var(--bg-card);
}

.param-label {
  font-family: var(--font);
  font-size: 0.78rem;
  color: var(--text);
}

.param-key {
  color: var(--text-muted);
  font-size: 0.68rem;
}

.param-value {
  font-weight: 600;
  color: #e8f4ff;
  text-align: right;
}

.param-unit {
  color: var(--text-dim);
  font-size: 0.62rem;
}

/* ── 空状态 ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 3rem;
  opacity: 0.5;
}

.empty-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text);
}

.empty-text {
  font-size: 0.82rem;
  color: var(--text-dim);
}

/* ── 按钮 ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 20px;
  border-radius: 7px;
  font-family: var(--font);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.25s;
}

.btn-primary {
  background: linear-gradient(135deg, #0277BD, #0288D1);
  color: #fff;
  box-shadow: 0 4px 14px rgba(2, 136, 209, 0.3);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(2, 136, 209, 0.5);
}

.btn-primary:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none !important;
}

.btn-ghost {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
}

.btn-ghost:hover {
  border-color: var(--border-hi);
  color: var(--text);
}
</style>
