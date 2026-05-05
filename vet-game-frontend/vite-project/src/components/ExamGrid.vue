<script setup lang="ts">
import type { Report } from "../types";

defineProps<{
  examinations: Record<string, { name: string; name_en: string; category: string; cost: number; description: string }>;
  examsDone: Set<string>;
  reports: Report[];
  loading: boolean;
}>();

const emit = defineEmits<{
  exam: [testType: string];
}>();
</script>

<template>
  <div class="panel-ttl">选择检查项目</div>
  <div class="exam-grid">
    <div
      v-for="(ex, key) in examinations"
      :key="key"
      :class="['ec', 'cat-' + ex.category, { done: examsDone.has(key) }]"
      @click="emit('exam', key)"
    >
      <div class="ec-name">{{ ex.name }}</div>
      <div class="ec-name-en">{{ ex.name_en }}</div>
      <div class="ec-desc">{{ ex.description }}</div>
      <div class="ec-cost">
        <template v-if="examsDone.has(key)"><span class="ec-done-mark">✓ 已完成</span></template>
        <template v-else>⚡ 消耗 {{ Math.max(1, ex.cost) }} 行动</template>
      </div>
    </div>
  </div>
  <div v-if="loading" class="loading">
    <div class="spinner"></div>
    <span class="loading-txt">正在获取检查结果...</span>
  </div>
</template>
