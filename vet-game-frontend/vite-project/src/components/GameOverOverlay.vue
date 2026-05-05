<script setup lang="ts">
import type { GameOverData } from "../types";

defineProps<{
  data: GameOverData;
  won: boolean;
  diseaseName: string;
}>();

const emit = defineEmits<{
  restart: [];
}>();
</script>

<template>
  <div class="overlay">
    <div class="overlay-card">
      <div class="ov-icon">{{ won ? "🏆" : "💔" }}</div>
      <div :class="['ov-title', won ? 'win' : 'lose']">{{ won ? "诊断正确！" : "很遗憾..." }}</div>
      <div class="ov-msg">{{ data.reason }}</div>

      <!-- 正确答案 -->
      <div class="answer-box" v-if="diseaseName">
        <div class="answer-label">正确诊断</div>
        <div class="answer-name">{{ diseaseName }}</div>
      </div>

      <!-- 评分 -->
      <div class="score-big" v-if="data.score">{{ data.score.total }} 分</div>
      <div class="score-gr" v-if="data.score">评级: {{ data.score.grade }}（消耗 {{ data.score.actions_used }} 行动）</div>

      <div class="btn-row" style="justify-content: center; margin-top: 8px">
        <button class="btn btn-primary" @click="emit('restart')">再来一局</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.answer-box {
  background: rgba(79, 195, 247, 0.06);
  border: 1px solid rgba(79, 195, 247, 0.2);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  text-align: center;
}
.answer-label {
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.answer-name {
  font-size: 1rem;
  font-weight: 700;
  color: var(--cyan);
}
</style>
