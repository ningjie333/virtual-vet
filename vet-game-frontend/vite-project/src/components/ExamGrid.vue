<script setup lang="ts">
import { computed } from "vue";
import type { Report } from "../types";

const props = defineProps<{
  examinations: Record<string, { name: string; name_en: string; category: string; tier: number; cost: number; description: string }>;
  examsDone: Set<string>;
  reports: Report[];
  loading: boolean;
  currentAp?: number;
}>();

const emit = defineEmits<{
  exam: [testType: string];
}>();

const tierLabels: Record<number, string> = {
  1: "基础检查",
  2: "快速检查",
  3: "核心诊断",
  4: "影像学",
  5: "金标准",
};

const tierColors: Record<number, string> = {
  1: "#4caf50",
  2: "#2196f3",
  3: "#ff9800",
  4: "#9c27b0",
  5: "#f44336",
};

const tierOrder = [1, 2, 3, 4, 5];

interface ExamEntry {
  key: string;
  ex: { name: string; name_en: string; category: string; tier: number; cost: number; description: string };
}

const groupedExams = computed(() => {
  const groups: { tier: number; label: string; exams: ExamEntry[] }[] = [];
  for (const tier of tierOrder) {
    const exams = Object.entries(props.examinations)
      .filter(([, ex]) => ex.tier === tier)
      .map(([key, ex]) => ({ key, ex }));
    if (exams.length > 0) {
      groups.push({ tier, label: tierLabels[tier] || `Tier ${tier}`, exams });
    }
  }
  return groups;
});

function canAfford(ex: { tier: number; cost: number }, currentAp: number): boolean {
  if (ex.tier >= 2) return currentAp >= ex.cost;
  return true; // Tier 1 always affordable (just costs action count)
}
</script>

<template>
  <div class="panel-ttl">选择检查项目</div>
  <div class="exam-groups">
    <div class="exam-group" v-for="group in groupedExams" :key="group.tier">
      <div class="exam-group-header" :style="{ borderColor: tierColors[group.tier] }">
        <span class="exam-group-dot" :style="{ background: tierColors[group.tier] }"></span>
        <span class="exam-group-label">{{ group.label }}</span>
        <span class="exam-group-count">{{ group.exams.length }} 项</span>
      </div>
      <div class="exam-grid">
        <div
          v-for="{ key, ex } in group.exams"
          :key="key"
          :class="['ec', { done: examsDone.has(key), disabled: !canAfford(ex, currentAp ?? 10) }]"
          @click="canAfford(ex, currentAp ?? 10) && emit('exam', key)"
        >
          <div class="ec-tier" :style="{ color: tierColors[ex.tier] }">
            T{{ ex.tier }}
          </div>
          <div class="ec-name">{{ ex.name }}</div>
          <div class="ec-name-en">{{ ex.name_en }}</div>
          <div class="ec-desc">{{ ex.description }}</div>
          <div class="ec-cost">
            <template v-if="examsDone.has(key)"><span class="ec-done-mark">✓ 已完成</span></template>
            <template v-else-if="ex.tier >= 2">
              ⚡ {{ ex.cost }} AP
            </template>
            <template v-else>
              🆓 免费（消耗 1 行动）
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div v-if="loading" class="loading">
    <div class="spinner"></div>
    <span class="loading-txt">正在获取检查结果...</span>
  </div>
</template>

<style scoped>
.exam-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.exam-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px solid;
  margin-bottom: 6px;
}
.exam-group-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.exam-group-label {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.exam-group-count {
  font-size: 0.55rem;
  opacity: 0.5;
  margin-left: auto;
}
.exam-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
}
.ec-tier {
  font-family: var(--mono);
  font-size: 0.55rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
}
.ec.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
