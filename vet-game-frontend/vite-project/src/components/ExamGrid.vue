<script setup lang="ts">
import type { Report } from "../types";

defineProps<{
  examinations: Record<string, { name: string; name_en: string; category: string; tier?: number; cost: number; description: string }>;
  examsDone: Set<string>;
  reports: Report[];
  loading: boolean;
  currentAp?: number;
}>();

const emit = defineEmits<{
  exam: [testType: string];
}>();

const tierLabels: Record<number, string> = {
  1: "基础",
  2: "快速",
  3: "核心",
  4: "影像",
  5: "金标",
};

const tierColors: Record<number, string> = {
  1: "#4caf50",
  2: "#2196f3",
  3: "#ff9800",
  4: "#9c27b0",
  5: "#f44336",
};

function apCost(ex: { tier?: number; cost: number }): number {
  if (ex.tier && ex.tier >= 2) return ex.cost;
  return 1; // Tier 0/1 still costs 1 action
}

function canAfford(ex: { tier?: number; cost: number }, currentAp: number): boolean {
  if (ex.tier && ex.tier >= 2) return currentAp >= ex.cost;
  return true; // Tier 0/1 always affordable (just costs action count)
}
</script>

<template>
  <div class="panel-ttl">选择检查项目</div>
  <div class="exam-grid">
    <div
      v-for="(ex, key) in examinations"
      :key="key"
      :class="['ec', 'cat-' + ex.category, { done: examsDone.has(key), disabled: !canAfford(ex, currentAp ?? 10) }]"
      @click="canAfford(ex, currentAp ?? 10) && emit('exam', key)"
    >
      <div class="ec-tier" v-if="ex.tier" :style="{ color: tierColors[ex.tier] }">
        T{{ ex.tier }} · {{ tierLabels[ex.tier] }}
      </div>
      <div class="ec-name">{{ ex.name }}</div>
      <div class="ec-name-en">{{ ex.name_en }}</div>
      <div class="ec-desc">{{ ex.description }}</div>
      <div class="ec-cost">
        <template v-if="examsDone.has(key)"><span class="ec-done-mark">✓ 已完成</span></template>
        <template v-else-if="ex.tier && ex.tier >= 2">
          ⚡ {{ ex.cost }} AP
        </template>
        <template v-else>
          🆓 免费（消耗 1 行动）
        </template>
      </div>
    </div>
  </div>
  <div v-if="loading" class="loading">
    <div class="spinner"></div>
    <span class="loading-txt">正在获取检查结果...</span>
  </div>
</template>

<style scoped>
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
