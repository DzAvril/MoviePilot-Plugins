<template>
  <v-card class="status-footer heat-glass-card" variant="flat">
    <div class="status-footer__content py-3 px-4 d-flex align-center justify-space-between text-caption text-medium-emphasis">
      <!-- Left: Last Update Time -->
      <div class="d-flex align-center">
        <v-badge
          dot
          :color="refreshing ? 'primary' : 'success'"
          inline
          class="mr-2 mb-0.5"
        ></v-badge>
        <span>
          最后检查时间: <span class="font-weight-bold text-high-emphasis">{{ lastUpdateTime || '未知' }}</span>
        </span>
      </div>

      <!-- Center/Right: Meta -->
      <div class="d-flex align-center gap-4">
        <!-- Plugin Meta -->
        <span class="d-none d-sm-inline-flex align-center">
          <v-icon size="14" class="mr-1">mdi-puzzle-outline</v-icon>
          <span>pluginheatmonitor v{{ version }}</span>
          <span class="mx-1.5">•</span>
          <span>By {{ author }}</span>
        </span>
      </div>
    </div>
  </v-card>
</template>

<script setup>
defineProps({
  lastUpdateTime: {
    type: String,
    default: ''
  },
  refreshing: {
    type: Boolean,
    default: false
  },
  version: {
    type: String,
    default: '1.7'
  },
  author: {
    type: String,
    default: 'DzAvril'
  }
})
</script>

<style scoped>
.status-footer {
  border-radius: 12px !important;
  transform: none !important;
  box-shadow: none !important;
  width: 100%;
}

.status-footer:hover {
  transform: none !important;
  box-shadow: none !important;
}

.gap-4 {
  gap: 16px;
}

.mb-0\.5 {
  margin-bottom: 2px;
}
</style>
