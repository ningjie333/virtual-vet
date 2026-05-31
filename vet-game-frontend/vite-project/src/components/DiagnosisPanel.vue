<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DiagnosisMatch, DiseaseReference, CriterionReference } from "../types";
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
const references = ref<Record<string, DiseaseReference>>({});
const expandedRefDisease = ref<string | null>(null);

function toggleRefDisease(disease: string) {
  expandedRefDisease.value = expandedRefDisease.value === disease ? null : disease;
}

function getCriteriaEntries(ref: DiseaseReference): [string, CriterionReference][] {
  const criteria = ref.matched_criteria || ref.criteria || {};
  return Object.entries(criteria);
}

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
  hepatic_failure_coagulopathy: "肝功能衰竭伴凝血障碍",
  splenic_rupture: "脾脏破裂",
  hyperthyroidism: "甲状腺功能亢进",
  hypoadrenocorticism: "肾上腺皮质功能减退",
  sepsis: "脓毒症",
  ivdd: "椎间盘疾病",
  meningitis: "脑膜炎/脑炎",
  ckd_anemia: "慢性肾病贫血",
  hepatic_anemia: "肝病贫血",
};

async function refreshDiagnosis() {
  if (!props.sessionId) return;
  diagLoading.value = true;
  try {
    const d = await api.getDiagnosis(props.sessionId);
    matches.value = d.matches;
    suggestedTests.value = d.suggested_tests;
    references.value = d.references || {};
  } finally {
    diagLoading.value = false;
  }
}

// 当 sessionId 变化时重置
watch(() => props.sessionId, () => {
  matches.value = [];
  suggestedTests.value = [];
  references.value = {};
  expandedRefDisease.value = null;
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

  <!-- 文献引用面板 -->
  <div class="ref-panel" v-if="Object.keys(references).length > 0">
    <div class="ref-title">📚 诊断依据</div>
    <div v-for="(ref, disease) in references" :key="disease" class="ref-disease">
      <button class="ref-disease-btn" @click="toggleRefDisease(disease)">
        <span>{{ diseaseNameMap[disease] || disease }}</span>
        <span class="ref-toggle">{{ expandedRefDisease === disease ? '▼' : '▶' }}</span>
      </button>
      <div class="ref-content" v-if="expandedRefDisease === disease">
        <!-- 指南引用 -->
        <div v-if="ref.guidelines.length > 0" class="ref-section">
          <div class="ref-section-title">核心指南</div>
          <div v-for="g in ref.guidelines" :key="g.title" class="ref-guideline">
            <span class="ref-authors">{{ g.authors }}</span>
            <span class="ref-year">({{ g.year }})</span>
            <span class="ref-title-text">{{ g.title }}.</span>
            <span class="ref-journal">*{{ g.journal }}*.</span>
            <span v-if="g.doi" class="ref-doi">DOI: {{ g.doi }}</span>
            <span v-else-if="g.pmid" class="ref-doi">PMID: {{ g.pmid }}</span>
          </div>
        </div>
        <!-- 诊断标准 -->
        <div v-if="getCriteriaEntries(ref).length > 0" class="ref-section">
          <div class="ref-section-title">诊断依据</div>
          <div v-for="([clue, criterion]) in getCriteriaEntries(ref)" :key="clue" class="ref-criterion">
            <div class="ref-clue-name">{{ clue }}</div>
            <div class="ref-criterion-detail">
              <span class="ref-threshold">{{ criterion.threshold }}</span>
              <span class="ref-source">[{{ criterion.source }}]</span>
            </div>
            <div class="ref-mechanism">{{ criterion.mechanism }}</div>
          </div>
        </div>
      </div>
    </div>
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

/* ── 文献引用面板 ── */
.ref-panel {
  background: rgba(255, 193, 7, 0.04);
  border: 1px solid rgba(255, 193, 7, 0.15);
  border-radius: 8px;
  padding: 10px 12px;
  margin-top: 10px;
}
.ref-title {
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  margin-bottom: 8px;
}
.ref-disease {
  margin-bottom: 6px;
}
.ref-disease-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  background: rgba(255, 193, 7, 0.06);
  border: 1px solid rgba(255, 193, 7, 0.12);
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
  transition: background 0.2s;
}
.ref-disease-btn:hover {
  background: rgba(255, 193, 7, 0.1);
}
.ref-toggle {
  font-size: 0.6rem;
  color: var(--text-muted);
}
.ref-content {
  margin-top: 6px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 6px;
}
.ref-section {
  margin-bottom: 8px;
}
.ref-section:last-child {
  margin-bottom: 0;
}
.ref-section-title {
  font-family: var(--mono);
  font-size: 0.55rem;
  color: var(--amber, #ffc107);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 4px;
}
.ref-guideline {
  font-size: 0.6rem;
  line-height: 1.5;
  color: var(--text-dim);
  margin-bottom: 4px;
  padding-left: 8px;
  border-left: 2px solid rgba(255, 193, 7, 0.2);
}
.ref-authors {
  color: var(--text);
}
.ref-year {
  color: var(--amber, #ffc107);
  margin: 0 2px;
}
.ref-title-text {
  color: var(--text-dim);
}
.ref-journal {
  color: var(--cyan);
  font-style: italic;
}
.ref-doi {
  display: block;
  font-family: var(--mono);
  font-size: 0.5rem;
  color: var(--text-muted);
  margin-top: 2px;
}
.ref-criterion {
  margin-bottom: 6px;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 4px;
}
.ref-clue-name {
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--cyan);
  margin-bottom: 2px;
}
.ref-criterion-detail {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin-bottom: 2px;
}
.ref-threshold {
  font-size: 0.6rem;
  color: var(--text);
  font-weight: 500;
}
.ref-source {
  font-size: 0.5rem;
  color: var(--text-muted);
  font-style: italic;
}
.ref-mechanism {
  font-size: 0.55rem;
  color: var(--text-dim);
  line-height: 1.4;
}
</style>
