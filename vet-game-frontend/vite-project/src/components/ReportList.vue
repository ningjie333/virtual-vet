<script setup lang="ts">
import { ref } from "vue";
import type { Report, ResultEntry } from "../types";

defineProps<{
  reports: Report[];
}>();

const openReports = ref(new Set<number>());

function toggle(i: number) {
  if (openReports.value.has(i)) {
    openReports.value.delete(i);
  } else {
    openReports.value.add(i);
  }
}

function flagText(f: string) {
  return ({ normal: "正常", low: "↓ 偏低", high: "↑ 偏高", critical: "⚠ 危急" }[f] || f);
}

function isResultEntryArray(results: ResultEntry[] | string[]): results is ResultEntry[] {
  return results.length > 0 && typeof results[0] === "object";
}
</script>

<template>
  <div class="panel-ttl">检查报告</div>
  <template v-if="reports.length === 0">
    <div style="color: var(--text-muted); font-size: 0.78rem; text-align: center; padding: 30px">
      尚未开具任何检查
    </div>
  </template>
  <template v-else>
    <div
      v-for="(r, i) in reports"
      :key="i"
      :class="['rc', { open: openReports.has(i) }]"
      @click="toggle(i)"
    >
      <div class="rc-hdr">
        <span class="rc-name">{{ r.name }}</span>
        <span class="rc-toggle">▼</span>
      </div>
      <div class="rc-body" @click.stop>
        <div class="rc-content">
          <div class="rc-summary">{{ r.summary }}</div>
          <table v-if="isResultEntryArray(r.results)" class="rc-table">
            <thead>
              <tr>
                <th>参数</th>
                <th>结果</th>
                <th>参考范围</th>
                <th>标记</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in r.results" :key="e.param">
                <td>{{ e.param }}</td>
                <td>{{ e.value }} {{ e.unit }}</td>
                <td>{{ e.normal_range }}</td>
                <td :class="'fl-' + e.flag">{{ flagText(e.flag) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else-if="r.results && r.results.length">
            <div
              v-for="s in r.results"
              :key="s"
              style="font-size: 0.75rem; color: var(--text-dim); padding: 2px 0"
            >
              · {{ s }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
