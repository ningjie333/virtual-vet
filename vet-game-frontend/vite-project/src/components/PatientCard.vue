<script setup lang="ts">
import type { Case } from "../types";

defineProps<{
  caseData: Case;
}>();
</script>

<template>
  <div class="panel-ttl">患宠信息</div>
  <div class="p-card">
    <div class="p-avatar">{{ caseData.animal.species === "犬" ? "🐕" : "🐱" }}</div>
    <div class="p-name">{{ caseData.animal.name }}</div>
    <div class="p-meta">
      {{ caseData.animal.breed }} · {{ caseData.animal.age }} · {{ caseData.animal.sex }} · {{ caseData.animal.weight_kg }}kg
    </div>
  </div>
  <div class="info-box complaint-box">
    <div class="lbl">主 诉</div>
    <div class="txt">{{ caseData.chief_complaint }}</div>
  </div>
  <div class="info-box history-box">
    <div class="lbl">病 史</div>
    <div class="txt">{{ caseData.history }}</div>
  </div>
</template>
