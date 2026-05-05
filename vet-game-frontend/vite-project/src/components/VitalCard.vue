<script setup lang="ts">
import { computed } from "vue";
import type { Vitals } from "../types";

const props = defineProps<{
  label: string;
  id: keyof Vitals;
  unit: string;
  warn: [number, number];
  danger: [number, number];
  vitals: Vitals;
  isNight?: boolean;
}>();

const cls = computed(() => {
  if (props.id === "HR_bpm" || props.id === "MAP_mmHg") return "v-cv";
  if (props.id === "GFR") return "v-renal";
  return "v-resp";
});

const displayVal = computed(() => {
  const v = props.vitals[props.id];
  return v != null ? String(v) : "—";
});

const vCls = computed(() => {
  const v = props.vitals[props.id];
  if (v == null) return "";
  if (typeof v !== "number") return "";
  if (v <= props.danger[0] || v >= props.danger[1]) return "danger";
  if (v <= props.warn[0] || v >= props.warn[1]) return "warn";
  return "";
});

const showNightHint = computed(() => props.isNight && props.id === "HR_bpm");
</script>

<template>
  <div class="v-card" :class="cls">
    <div class="v-lbl">{{ label }}</div>
    <div :class="['v-val', vCls]">{{ displayVal }}</div>
    <div class="v-unit">{{ unit }}</div>
    <div v-if="showNightHint" class="hint-night">🌙 夜间生理性心动过缓</div>
  </div>
</template>
