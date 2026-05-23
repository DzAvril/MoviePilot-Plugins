<template>
  <div
    class="plugin-list-item cursor-pointer transition-all"
    :class="{ 'plugin-list-item--active': isActive }"
    @click="$emit('click')"
  >
    <!-- Left: Avatar -->
    <v-avatar size="36" class="plugin-avatar">
      <v-img :src="plugin.plugin_icon || plugin.icon" v-if="plugin.plugin_icon || plugin.icon">
        <template v-slot:placeholder>
          <div class="avatar-placeholder">
            <v-icon color="primary" size="20">mdi-puzzle-outline</v-icon>
          </div>
        </template>
      </v-img>
      <div v-else class="avatar-placeholder">
        <v-icon color="primary" size="20">mdi-puzzle-outline</v-icon>
      </div>
    </v-avatar>

    <!-- Center/Right: Details and Progress -->
    <div class="plugin-list-item__content">
      <div class="plugin-list-item__header">
        <span class="plugin-list-item__name text-truncate">
          {{ plugin.plugin_name || plugin.name }}
        </span>
        <v-chip size="x-small" color="primary" variant="flat" class="plugin-list-item__downloads">
          {{ (plugin.current_downloads || plugin.downloads || 0).toLocaleString() }}
        </v-chip>
      </div>

      <!-- Description -->
      <div v-if="plugin.desc" class="plugin-list-item__desc text-truncate">
        {{ plugin.desc }}
      </div>
      
      <!-- Progress Bar showing download progress towards notification threshold -->
      <div class="mt-1">
        <ProgressBar
          :current="plugin.increment_since_last || 0"
          :target="plugin.download_increment || 100"
          unit=""
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import ProgressBar from './ProgressBar.vue'

const props = defineProps({
  plugin: {
    type: Object,
    required: true
  },
  isActive: {
    type: Boolean,
    default: false
  }
})

defineEmits(['click'])
</script>

<style scoped>
.plugin-list-item {
  display: flex !important;
  align-items: center !important;
  padding: 10px 12px !important;
  margin-bottom: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background-color: rgb(var(--v-theme-surface));
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
}

.plugin-list-item:hover {
  transform: translateX(4px);
  border-color: rgb(var(--v-theme-primary));
  background-color: rgba(var(--v-theme-primary), 0.03);
  box-shadow: var(--heat-shadow-sm);
}

.plugin-list-item--active {
  border-color: rgb(var(--v-theme-primary)) !important;
  background-color: rgba(var(--v-theme-primary), 0.08) !important;
  box-shadow: var(--heat-shadow-md);
}

.plugin-avatar {
  flex-shrink: 0;
  margin-right: 12px;
  border: 1.5px solid rgba(var(--v-theme-primary), 0.15);
  background-color: rgba(var(--v-theme-on-surface), 0.02);
  transition: all 0.3s ease;
}

.plugin-list-item:hover .plugin-avatar {
  transform: scale(1.08) rotate(5deg);
  border-color: rgb(var(--v-theme-primary));
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  background-color: rgba(var(--v-theme-primary), 0.05);
}

.plugin-list-item__content {
  flex-grow: 1;
  min-width: 0;
}

.plugin-list-item__header {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  margin-bottom: 4px;
}

.plugin-list-item__name {
  font-size: 13px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.85);
  margin-right: 8px;
}

.plugin-list-item__downloads {
  font-weight: 700 !important;
  flex-shrink: 0;
}

.plugin-list-item__desc {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  margin-bottom: 2px;
  line-height: 1.3;
}
</style>
