<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DiagnosisMatch } from "../types";
import { api } from "../api";

const diagnosis = defineModel<string>({ default: "" });

const props = defineProps<{
  hint: string;
  hintClass: string;
  treatments: Record<string, { name: string; description: string; correct_for: string | null }>;
  sessionId: string;
  refreshTrigger: number;
}>();

const emit = defineEmits<{
  submit: [];
  hint: [];
  supportiveCare: [];
}>();

const hasSupportiveCare = computed(() => "supportive_care" in props.treatments);

const diagnosisOptions = computed(() =>
  Object.entries(props.treatments)
    .filter(([, v]) => v.correct_for !== null)
    .map(([key, v]) => ({
      value: key,
      label: diseaseNameMap[v.correct_for!] || v.correct_for!,
    }))
);

// ── 置信度面板 ──
const matches = ref<DiagnosisMatch[]>([]);
const suggestedTests = ref<string[]>([]);
const diagLoading = ref(false);

const diseaseNameMap: Record<string, string> = {
  pneumonia: "肺炎",
  acute_renal_failure: "急性肾衰竭",
  dilated_cardiomyopathy: "扩张型心肌病（DCM）",
};

async function refreshDiagnosis() {
  if (!props.sessionId) return;
  diagLoading.value = true;
  try {
    const d = await api.getDiagnosis(props.sessionId);
    matches.value = d.matches;
    suggestedTests.value = d.suggested_tests;
  } finally {
    diagLoading.value = false;
  }
}

// 当 sessionId 变化时重置
watch(() => props.sessionId, () => {
  matches.value = [];
  suggestedTests.value = [];
}, { immediate: true });

// 当 refreshTrigger 变化时自动刷新诊断
watch(() => props.refreshTrigger, () => {
  if (props.refreshTrigger > 0) {
    refreshDiagnosis();
  }
});
</script>

<template>
  <div class="panel-ttl">做出诊断</div>

  <!-- 置信度面板 -->
  <div class="conf-panel" v-if="matches.length > 0">
    <div class="conf-title">鉴别诊断</div>
    <div
      v-for="m in matches"
      :key="m.disease"
      :class="['conf-row', { 'conf-top': m.confidence === matches[0]?.confidence && m.confidence > 0 }]"
    >
      <span class="conf-name">{{ diseaseNameMap[m.disease] || m.disease }}</span>
      <span class="conf-pct">{{ (m.confidence * 100).toFixed(0) }}%</span>
      <div class="conf-bar">
        <div class="conf-bar-fill" :style="{ width: (m.confidence * 100) + '%' }"></div>
      </div>
    </div>
    <div class="conf-tests" v-if="suggestedTests.length > 0">
      <span class="conf-tests-label">建议检查：</span>
      <span class="conf-tests-item" v-for="t in suggestedTests" :key="t">{{ t }}</span>
    </div>
    <button class="btn btn-ghost conf-refresh" @click="refreshDiagnosis" :disabled="diagLoading">
      {{ diagLoading ? "刷新中..." : "🔄 刷新诊断" }}
    </button>
  </div>

  <div class="diag-row">
    <span class="diag-label">你的诊断：</span>
    <select class="diag-select" v-model="diagnosis">
      <option value="">-- 选择最可能的疾病 --</option>
      <option v-for="opt in diagnosisOptions" :key="opt.value" :value="opt.value">
        {{ opt.label }}
      </option>
    </select>
  </div>
  <div class="btn-row">
    <button class="btn btn-primary" :disabled="!diagnosis" @click="emit('submit')">
      💊 确认诊断
    </button>
    <button class="btn btn-ghost" @click="emit('hint')">💡 查看提示</button>
  </div>
  <div class="btn-row" v-if="hasSupportiveCare" style="margin-top: 6px">
    <button class="btn btn-ghost" style="width: 100%" @click="emit('supportiveCare')">
      💧 支持治疗（补液 200 mL，不消耗诊断机会）
    </button>
  </div>
  <div v-if="hint" style="margin-top: 8px">
    <div :class="['hint-box', hintClass]" v-text="hint"></div>
  </div>
</template>

<style scoped>
.conf-panel {
  background: rgba(79, 195, 247, 0.04);
  border: 1px solid rgba(79, 195, 247, 0.15);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.conf-title {
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.conf-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
  align-items: center;
  padding: 3px 0;
}
.conf-top .conf-name {
  color: var(--cyan);
  font-weight: 600;
}
.conf-pct {
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--text-dim);
  text-align: right;
}
.conf-bar {
  grid-column: 1 / -1;
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
}
.conf-bar-fill {
  height: 100%;
  background: var(--cyan);
  border-radius: 2px;
  transition: width 0.3s ease;
}
.conf-top .conf-bar-fill {
  background: var(--green, #4caf50);
}
.conf-tests {
  margin-top: 6px;
  font-size: 0.65rem;
  color: var(--text-muted);
}
.conf-tests-label {
  margin-right: 4px;
}
.conf-tests-item {
  display: inline-block;
  background: rgba(79, 195, 247, 0.1);
  border: 1px solid rgba(79, 195, 247, 0.2);
  border-radius: 4px;
  padding: 1px 6px;
  margin: 2px 2px;
  font-family: var(--mono);
  font-size: 0.55rem;
}
.conf-refresh {
  margin-top: 6px;
  width: 100%;
  font-size: 0.65rem;
}
</style>
