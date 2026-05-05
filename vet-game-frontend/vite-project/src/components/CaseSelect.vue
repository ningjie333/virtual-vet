<script setup lang="ts">
import type { Case } from "../types";

defineProps<{
  cases: Case[];
}>();

const emit = defineEmits<{
  select: [caseId: string];
}>();
</script>

<template>
  <div class="case-select">
    <h2>选择病例</h2>
    <p>你是一名兽医，请根据患宠的临床表现做出诊断并制定治疗方案。</p>
    <div class="case-cards">
      <div v-for="c in cases" :key="c.id" class="cc" @click="emit('select', c.id)">
        <div class="cc-title">{{ c.title }}</div>
        <div class="cc-diff">{{ c.difficulty_label }} · {{ c.animal.breed }} · {{ c.animal.weight_kg }}kg</div>
        <div class="cc-desc">{{ c.chief_complaint }}</div>
      </div>
    </div>
  </div>
</template>
