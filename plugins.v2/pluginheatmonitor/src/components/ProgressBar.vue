<template>
  <div class="heat-progress-container w-100">
    <div class="d-flex align-center justify-space-between mb-1 text-caption text-medium-emphasis font-weight-medium">
      <span class="text-truncate">{{ label }}</span>
      <span class="font-weight-bold ml-2">
        {{ current.toLocaleString() }} / {{ target.toLocaleString() }}{{ unit }}
        <span class="ml-1 text-primary">({{ progressPercent }}%)</span>
      </span>
    </div>
    
    <div class="progress-bar-track position-relative">
      <div 
        class="progress-bar-fill" 
        :class="fillClass"
        :style="{ width: `${clampedPercent}%` }"
      >
        <!-- Completed shine effect -->
        <div v-if="isCompleted" class="shine-effect"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  current: {
    type: Number,
    required: true
  },
  target: {
    type: Number,
    required: true,
    default: 100
  },
  label: {
    type: String,
    default: ''
  },
  unit: {
    type: String,
    default: ''
  }
})

const progressPercent = computed(() => {
  if (!props.target || props.target <= 0) return 0
  const pct = (props.current / props.target) * 100
  return Math.min(Math.round(pct), 1000) // 允许超过100%，但在轨道上限制为100%
})

const clampedPercent = computed(() => {
  return Math.min(progressPercent.value, 100)
})

const isCompleted = computed(() => {
  return progressPercent.value >= 100
})

const fillClass = computed(() => {
  const pct = progressPercent.value
  if (pct >= 100) return 'progress-fill--completed'
  if (pct >= 80) return 'progress-fill--success'
  if (pct >= 30) return 'progress-fill--primary'
  return 'progress-fill--default'
})
</script>

<style scoped>
.heat-progress-container {
  font-family: inherit;
}

.progress-bar-track {
  height: 6px;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 3px;
  overflow: hidden;
  width: 100%;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

/* 颜色区间样式 */
.progress-fill--default {
  background-color: rgba(var(--v-theme-on-surface), 0.35);
}

.progress-fill--primary {
  background-color: rgb(var(--v-theme-primary));
}

.progress-fill--success {
  background-color: rgb(var(--v-theme-success));
}

.progress-fill--completed {
  background: linear-gradient(90deg, #10B981, #059669, #10B981);
  background-size: 200% 100%;
  animation: completedGlow 2s infinite linear;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
}

/* 100% 完成扫光动画 */
.shine-effect {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0) 0%,
    rgba(255, 255, 255, 0.4) 50%,
    rgba(255, 255, 255, 0) 100%
  );
  transform: translateX(-100%);
  animation: shine 1.5s infinite ease-in-out;
}

@keyframes shine {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@keyframes completedGlow {
  0% { background-position: 0% 50%; }
  100% { background-position: 200% 50%; }
}
</style>
