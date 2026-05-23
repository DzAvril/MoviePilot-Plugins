<template>
  <v-card
    class="stats-card heat-glass-card overflow-hidden h-100"
    :class="{ 'stats-card--loading': loading }"
    variant="flat"
  >
    <v-card-text class="pa-4 position-relative fill-height d-flex flex-column justify-space-between">
      <!-- Loading Skeleton -->
      <div v-if="loading" class="skeleton-wrapper">
        <div class="skeleton-icon mb-3"></div>
        <div class="skeleton-line skeleton-label mb-2"></div>
        <div class="skeleton-line skeleton-value mb-1"></div>
        <div class="skeleton-line skeleton-subtitle"></div>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-wrapper d-flex flex-column align-center justify-center fill-height py-2 text-center">
        <v-icon color="error" size="32" class="mb-2">mdi-alert-circle-outline</v-icon>
        <span class="text-caption text-error font-weight-medium">{{ errorMessage || '加载失败' }}</span>
      </div>

      <!-- Empty State -->
      <div v-else-if="empty" class="empty-wrapper d-flex flex-column align-center justify-center fill-height py-2 text-center">
        <v-icon color="grey-lighten-1" size="32" class="mb-2">mdi-inbox-outline</v-icon>
        <span class="text-caption text-medium-emphasis">无数据</span>
      </div>

      <!-- Content State -->
      <div v-else class="content-wrapper d-flex flex-column justify-space-between fill-height">
        <!-- Top row: icon and trend -->
        <div class="d-flex align-center justify-space-between mb-3">
          <div
            class="icon-bg d-flex align-center justify-center"
            :style="{ backgroundColor: `rgba(var(--v-theme-${color}), 0.12)` }"
          >
            <v-icon :color="color" size="24">{{ icon }}</v-icon>
          </div>
          
          <div v-if="trend !== undefined && trend !== null && trend !== ''" class="trend-badge d-flex align-center">
            <span
              class="text-caption font-weight-bold d-flex align-center"
              :class="isPositiveTrend ? 'text-success' : 'text-grey'"
            >
              <v-icon size="14" class="mr-1">
                {{ isPositiveTrend ? 'mdi-arrow-up-bold' : 'mdi-arrow-right-bold' }}
              </v-icon>
              {{ trend }}
            </span>
          </div>
        </div>

        <!-- Label -->
        <div class="text-caption text-uppercase font-weight-medium text-medium-emphasis mb-1 tracking-wider">
          {{ label }}
        </div>

        <!-- Value -->
        <div class="text-h4 font-weight-bold text-high-emphasis tracking-tight my-1">
          {{ formattedValue }}
        </div>

        <!-- Subtitle -->
        <div class="text-caption text-medium-emphasis text-truncate mt-1" v-if="subtitle">
          {{ subtitle }}
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: {
    type: String,
    required: true
  },
  value: {
    type: [String, Number],
    default: '0'
  },
  subtitle: {
    type: String,
    default: ''
  },
  color: {
    type: String,
    default: 'primary'
  },
  icon: {
    type: String,
    default: 'mdi-help-circle'
  },
  trend: {
    type: [String, Number],
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: Boolean,
    default: false
  },
  errorMessage: {
    type: String,
    default: '数据异常'
  },
  empty: {
    type: Boolean,
    default: false
  }
})

const isPositiveTrend = computed(() => {
  const t = String(props.trend)
  return t.includes('+') || (parseFloat(t) > 0)
})

const formattedValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString()
  }
  return props.value
})
</script>

<style scoped>
.stats-card {
  min-width: 180px;
  border-radius: 16px !important;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.icon-bg {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  transition: all 0.3s ease;
}

.stats-card:hover .icon-bg {
  transform: scale(1.08);
}

.trend-badge {
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(var(--v-theme-surface-variant), 0.05);
}

/* Skeleton Loading Styles */
.skeleton-wrapper {
  width: 100%;
}

.skeleton-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(90deg, rgba(var(--v-theme-on-surface), 0.06) 25%, rgba(var(--v-theme-on-surface), 0.12) 50%, rgba(var(--v-theme-on-surface), 0.06) 75%);
  background-size: 200% 100%;
  animation: loadingShimmer 1.5s infinite;
}

.skeleton-line {
  background: linear-gradient(90deg, rgba(var(--v-theme-on-surface), 0.06) 25%, rgba(var(--v-theme-on-surface), 0.12) 50%, rgba(var(--v-theme-on-surface), 0.06) 75%);
  background-size: 200% 100%;
  animation: loadingShimmer 1.5s infinite;
  border-radius: 4px;
}

.skeleton-label {
  width: 50%;
  height: 14px;
}

.skeleton-value {
  width: 75%;
  height: 28px;
}

.skeleton-subtitle {
  width: 90%;
  height: 12px;
}

@keyframes loadingShimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.fill-height {
  height: 100%;
}
</style>
