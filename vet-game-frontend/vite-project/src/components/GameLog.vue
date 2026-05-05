<script setup lang="ts">
defineProps<{
  entries: string[];
}>();
</script>

<template>
  <div class="glog" v-if="entries.length">
    <div class="glog-title">// 诊疗日志</div>
    <div v-for="(e, i) in entries" :key="i" class="glog-entry">{{ e }}</div>
  </div>
</template>
