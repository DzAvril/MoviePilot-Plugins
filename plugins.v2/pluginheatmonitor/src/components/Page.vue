<template>
  <v-container fluid class="heat-page-container pa-2 pa-sm-4 max-width-xl mx-auto">
    <!-- Topbar -->
    <div class="heat-topbar mb-3">
      <div class="heat-topbar__left">
        <div class="heat-topbar__icon">
          <v-icon size="24">mdi-chart-timeline-variant</v-icon>
        </div>
        <div class="heat-topbar__meta">
          <div class="heat-topbar__title">插件热度监控</div>
          <div class="heat-topbar__sub">实时监控已安装插件下载量增量与热度分布</div>
        </div>
      </div>
      <div class="heat-topbar__right">
        <v-btn-group variant="tonal" density="compact" class="elevation-0">
          <v-btn color="primary" @click="refreshData" :loading="refreshing" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon size="18" class="mr-sm-1">mdi-refresh</v-icon>
            <span class="btn-text d-none d-sm-inline">刷新</span>
          </v-btn>
          <v-btn color="primary" @click="goToConfig" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon size="18" class="mr-sm-1">mdi-cog-outline</v-icon>
            <span class="btn-text d-none d-sm-inline">设置</span>
          </v-btn>
          <v-btn color="primary" @click="emit('close')" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon size="18" class="mr-sm-1">mdi-close</v-icon>
            <span class="btn-text d-none d-sm-inline">关闭</span>
          </v-btn>
        </v-btn-group>
      </div>
    </div>

    <!-- Global Stats Overview -->
    <v-row class="grid-gap-12 mb-1">
      <!-- Card 1: Monitored Plugins -->
      <v-col cols="3" class="grid-col-gap-12">
        <v-card class="premium-stat-card card-primary" variant="flat">
          <div class="premium-stat-card__body">
            <div class="premium-stat-card__info">
              <span class="premium-stat-card__label">监控插件</span>
              <span class="premium-stat-card__value text-primary">
                <span v-if="loading" class="stats-panel-skeleton"></span>
                <span v-else>{{ monitoredPlugins.length }} <span class="unit-text">个</span></span>
              </span>
            </div>
            <div class="premium-stat-card__icon text-primary d-none d-sm-flex">
              <v-icon size="22">mdi-puzzle-outline</v-icon>
            </div>
          </div>
        </v-card>
      </v-col>

      <!-- Card 2: Total Downloads -->
      <v-col cols="3" class="grid-col-gap-12">
        <v-card class="premium-stat-card card-success" variant="flat">
          <div class="premium-stat-card__body">
            <div class="premium-stat-card__info">
              <span class="premium-stat-card__label">总下载量</span>
              <span class="premium-stat-card__value text-success">
                <span v-if="loading" class="stats-panel-skeleton"></span>
                <span v-else>{{ totalDownloads.toLocaleString() }}</span>
              </span>
            </div>
            <div class="premium-stat-card__icon text-success d-none d-sm-flex">
              <v-icon size="22">mdi-download-outline</v-icon>
            </div>
          </div>
        </v-card>
      </v-col>

      <!-- Card 3: Daily Growth -->
      <v-col cols="3" class="grid-col-gap-12">
        <v-card class="premium-stat-card card-info" variant="flat">
          <div class="premium-stat-card__body">
            <div class="premium-stat-card__info">
              <span class="premium-stat-card__label">今日新增</span>
              <span class="premium-stat-card__value text-info">
                <span v-if="loading" class="stats-panel-skeleton"></span>
                <span v-else>+{{ totalGrowth.toLocaleString() }}</span>
              </span>
            </div>
            <div class="premium-stat-card__icon text-info d-none d-sm-flex">
              <v-icon size="22">mdi-trending-up</v-icon>
            </div>
          </div>
        </v-card>
      </v-col>

      <!-- Card 4: Last Check -->
      <v-col cols="3" class="grid-col-gap-12">
        <v-card class="premium-stat-card card-warning" variant="flat">
          <div class="premium-stat-card__body">
            <div class="premium-stat-card__info">
              <span class="premium-stat-card__label">最近检查</span>
              <span class="premium-stat-card__value text-warning">
                <span v-if="loading" class="stats-panel-skeleton"></span>
                <span v-else>{{ formattedLastCheck }}</span>
              </span>
            </div>
            <div class="premium-stat-card__icon text-warning d-none d-sm-flex">
              <v-icon size="22">mdi-clock-outline</v-icon>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Main Workspace Layout -->
    <div v-if="loading" class="d-flex justify-center align-center py-12">
      <div class="text-center">
        <v-progress-circular indeterminate color="primary" size="48" class="mb-3"></v-progress-circular>
        <div class="text-body-2 text-medium-emphasis">载入数据中，请稍候...</div>
      </div>
    </div>

    <v-row v-else class="heat-animate-scale-in grid-gap-12">
      <!-- Left Column: Core charts and Selected details -->
      <v-col cols="12" lg="8" xl="9" class="grid-col-gap-12">
        <!-- Main views card (Heatmap & Trend) -->
        <PluginDetail
          v-if="selectedPlugin"
          :plugin="selectedPlugin"
          :api="api"
          class="main-chart-card heat-glass-card"
          ref="pluginDetailRef"
          @data-changed="loadData"
        />

      </v-col>

      <!-- Right Column: Monitored Plugin List -->
      <v-col cols="12" lg="4" xl="3" class="grid-col-gap-12">
        <v-card class="plugin-sidebar-card heat-glass-card" variant="flat">
          <!-- Card Header using identical padding as left card -->
          <div class="pa-2 pa-sm-4 pb-0">
            <div class="d-flex align-center justify-space-between flex-wrap gap-2 width-100">
              <div class="d-flex align-center gap-1">
                <span class="text-subtitle-1 font-weight-bold">已监控 {{ monitoredPlugins.length }} 个插件</span>
              </div>
              
              <v-menu location="bottom end">
                <template v-slot:activator="{ props }">
                  <v-btn
                    variant="text"
                    size="small"
                    color="primary"
                    v-bind="props"
                    prepend-icon="mdi-sort"
                    class="px-2 font-weight-bold text-caption"
                  >
                    {{ currentSortLabel }}
                  </v-btn>
                </template>
                <v-list density="compact">
                  <v-list-item
                    v-for="opt in sortOptions"
                    :key="opt.value"
                    @click="sortBy = opt.value"
                    :active="sortBy === opt.value"
                    color="primary"
                  >
                    <v-list-item-title class="text-caption font-weight-medium">{{ opt.title }}</v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-menu>
            </div>
          </div>

          <v-card-text class="pa-2 pa-sm-4 pt-0 plugin-list-scroll">
            <div v-if="monitoredPlugins.length === 0" class="text-center py-8">
              <v-icon color="grey-lighten-1" size="36">mdi-puzzle-outline</v-icon>
              <div class="text-caption text-medium-emphasis mt-2">暂无监控插件</div>
              <v-btn size="x-small" color="primary" variant="text" class="mt-1" @click="goToConfig">
                立即去配置
              </v-btn>
            </div>

            <div v-else>
              <PluginListItem
                v-for="plugin in sortedPlugins"
                :key="plugin.plugin_id || plugin.id"
                :plugin="plugin"
                :is-active="selectedPlugin && (selectedPlugin.id || selectedPlugin.plugin_id) === (plugin.id || plugin.plugin_id)"
                @click="selectPlugin(plugin)"
              />
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Global Footer -->
    <v-row class="grid-gap-12 mt-1">
      <v-col cols="12" class="grid-col-gap-12">
        <StatusFooter
          :last-update-time="lastUpdateTime"
          :refreshing="refreshing"
          :version="pluginVersion || undefined"
          :running="running"
          @run-once="runOnce"
        />
      </v-col>
    </v-row>

    <!-- Alert toast -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.message }}
    </v-snackbar>
  </v-container>
</template>

<script setup>
import '../styles/tokens.css'
import { ref, reactive, computed, onMounted, watch } from 'vue'
import StatsCard from './StatsCard.vue'
import PluginListItem from './PluginListItem.vue'
import StatusFooter from './StatusFooter.vue'
import PluginDetail from './PluginDetail.vue'

const props = defineProps({
  api: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['switch', 'close'])

// State
const loading = ref(true)
const refreshing = ref(false)
const monitoredPlugins = ref([])
const totalDownloads = ref(0)
const totalGrowth = ref(0)
const lastUpdateTime = ref('')
const selectedPlugin = ref(null)
const sortBy = ref('downloads')
const pluginVersion = ref('')
const running = ref(false)

const pluginDetailRef = ref(null)

const sortOptions = [
  { title: '下载量降序', value: 'downloads' },
  { title: '增量进度降序', value: 'progress' },
  { title: '插件名称', value: 'name' }
]

const currentSortLabel = computed(() => {
  const option = sortOptions.find(opt => opt.value === sortBy.value)
  return option ? option.title : '排序方式'
})

const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})

// Format helpers
const formattedLastCheck = computed(() => {
  if (!lastUpdateTime.value) return '未知'
  // Clean up timestamp if contains date
  const parts = lastUpdateTime.value.split(' ')
  return parts.length > 1 ? parts[1] : lastUpdateTime.value
})

// Sorting computation
const sortedPlugins = computed(() => {
  const list = [...monitoredPlugins.value]
  if (sortBy.value === 'downloads') {
    return list.sort((a, b) => b.downloads - a.downloads)
  }
  if (sortBy.value === 'progress') {
    return list.sort((a, b) => {
      const progA = (a.increment_since_last || 0) / (a.download_increment || 100)
      const progB = (b.increment_since_last || 0) / (b.download_increment || 100)
      return progB - progA
    })
  }
  if (sortBy.value === 'name') {
    return list.sort((a, b) => (a.plugin_name || a.name || '').localeCompare(b.plugin_name || b.name || ''))
  }
  return list
})

// Notification helper
function showMessage(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function goToConfig() {
  emit('switch')
}

function handleSquareClicked(data) {
  if (data.square && data.plugin) {
    const date = data.square.date.toLocaleDateString('zh-CN')
    const message = `${data.plugin.plugin_name || data.plugin.name} - ${date}: +${data.square.value} downloads`
    showMessage(message, 'info')
  }
}

// Select plugin for detail visualization
function selectPlugin(plugin) {
  selectedPlugin.value = plugin
}

// Load status data
async function loadData() {
  try {
    const statusData = await props.api.get('plugin/PluginHeatMonitor/status')
    if (statusData) {
      monitoredPlugins.value = statusData.monitored_plugins || []
      totalDownloads.value = statusData.total_downloads || 0
      lastUpdateTime.value = statusData.global_last_check_time || ''
      totalGrowth.value = statusData.total_daily_growth || 0
      pluginVersion.value = statusData.version || ''

      if (monitoredPlugins.value.length > 0) {
        const stillExists = selectedPlugin.value && monitoredPlugins.value.some(
          p => (p.id || p.plugin_id) === (selectedPlugin.value.id || selectedPlugin.value.plugin_id)
        )
        if (!stillExists) {
          selectedPlugin.value = sortedPlugins.value[0]
        } else {
          const freshPlugin = monitoredPlugins.value.find(
            p => (p.id || p.plugin_id) === (selectedPlugin.value.id || selectedPlugin.value.plugin_id)
          )
          if (freshPlugin) {
            selectedPlugin.value = freshPlugin
          }
        }
      } else {
        selectedPlugin.value = null
      }
    }
  } catch (error) {
    console.error('加载监控主页数据失败:', error)
    showMessage('获取服务状态失败', 'error')
  }
}

async function refreshData() {
  refreshing.value = true
  try {
    await loadData()
    if (pluginDetailRef.value && typeof pluginDetailRef.value.loadDetailData === 'function') {
      await pluginDetailRef.value.loadDetailData()
    }
    showMessage('热度状态已最新')
  } catch (error) {
    showMessage('刷新失败', 'error')
  } finally {
    refreshing.value = false
  }
}

async function runOnce() {
  running.value = true
  try {
    const response = await props.api.post('plugin/PluginHeatMonitor/run_once')
    if (response && response.status === 'success') {
      showMessage('已触发立即运行')
      setTimeout(() => {
        refreshData()
      }, 1500)
    } else {
      showMessage(response?.message || '触发失败', 'error')
    }
  } catch (error) {
    console.error('触发立即运行失败:', error)
    showMessage('触发立即运行失败', 'error')
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  loading.value = true
  await loadData()
  loading.value = false
})
</script>

<style scoped>
.heat-page-container {
  max-width: 1400px;
}

.heat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 8px;
}

.heat-topbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.heat-topbar__meta {
  min-width: 0;
  flex: 1;
}

.heat-topbar__right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.heat-topbar__icon {
  width: 42px;
  height: 42px;
  border-radius: 11px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.heat-topbar__title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.3px;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.heat-topbar__sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .heat-topbar {
    align-items: center;
    flex-wrap: nowrap;
  }

  .heat-topbar__left {
    min-width: 0;
    flex: 1;
  }

  .heat-topbar__meta {
    min-width: 0;
  }

  .heat-topbar__right {
    justify-content: flex-end;
    flex-shrink: 0;
  }
}

.main-chart-card,
.plugin-sidebar-card {
  border-radius: 12px !important;
  box-shadow: none !important;
  transform: none !important;
  display: flex;
  flex-direction: column;
}

/* On lg+, both cards are side by side — fix height so they align */
@media (min-width: 1280px) {
  .main-chart-card,
  .plugin-sidebar-card {
    height: 460px !important;
  }
}

/* On mobile/tablet, chart card grows with content */
@media (max-width: 1279px) {
  .main-chart-card {
    height: auto !important;
  }

  .plugin-sidebar-card {
    height: 460px !important;
  }
}

.grid-gap-12 {
  margin-left: -6px !important;
  margin-right: -6px !important;
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}

.grid-col-gap-12 {
  padding: 6px !important;
}

.main-chart-card-text {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.view-toggle-btn {
  height: 28px !important;
  min-height: 28px !important;
  font-size: 11px !important;
  padding: 0 8px !important;
}

.trend-data-chip {
  height: 20px !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  padding: 0 8px !important;
}

.plugin-select-header {
  width: 140px;
  max-width: 160px;
}

.plugin-select-header :deep(.v-field) {
  border-radius: 6px !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  height: 24px !important;
  min-height: 24px !important;
  background: rgba(var(--v-theme-primary), 0.05);
  box-shadow: none !important;
  border-color: rgba(var(--v-theme-primary), 0.12) !important;
}

.plugin-select-header :deep(.v-field__input) {
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  min-height: 24px !important;
  height: 24px !important;
  line-height: 24px !important;
  display: flex !important;
  align-items: center !important;
}

.plugin-select-header :deep(.v-field__append-inner) {
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  align-items: center !important;
  height: 24px !important;
}

.plugin-select-header :deep(.v-field__append-inner .v-icon) {
  font-size: 14px !important;
}

.year-chip-group-header {
  padding: 0 !important;
  margin: 0 !important;
  height: 20px !important;
  min-height: 20px !important;
}

.year-chip-group-header :deep(.v-slide-group__content) {
  gap: 4px;
}

.main-chart-card:hover,
.plugin-sidebar-card:hover {
  transform: none !important;
  box-shadow: none !important;
}

.premium-stat-card {
  border-radius: 12px !important;
  box-shadow: none !important;
  transform: none !important;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid transparent !important;
}

.premium-stat-card__body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  min-height: 64px;
}

@media (max-width: 599px) {
  .premium-stat-card__body {
    padding: 8px 10px;
    min-height: 52px;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }

  .premium-stat-card__label {
    font-size: 9px !important;
  }

  .premium-stat-card__value {
    font-size: 14px !important;
  }
}

.premium-stat-card__info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.premium-stat-card__label {
  font-size: 10.5px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.55);
  letter-spacing: 0.2px;
}

.premium-stat-card__value {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.25;
  margin-top: 2px;
  letter-spacing: -0.3px;
}

.unit-text {
  font-size: 12px;
  font-weight: 500;
  opacity: 0.7;
}

.premium-stat-card__icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  opacity: 0.85;
}

/* Card Primary */
.card-primary {
  background: rgba(var(--v-theme-primary), 0.05) !important;
  border-color: rgba(var(--v-theme-primary), 0.12) !important;
}
.card-primary:hover {
  background: rgba(var(--v-theme-primary), 0.08) !important;
  border-color: rgba(var(--v-theme-primary), 0.2) !important;
}

/* Card Success */
.card-success {
  background: rgba(var(--v-theme-success), 0.05) !important;
  border-color: rgba(var(--v-theme-success), 0.12) !important;
}
.card-success:hover {
  background: rgba(var(--v-theme-success), 0.08) !important;
  border-color: rgba(var(--v-theme-success), 0.2) !important;
}

/* Card Info */
.card-info {
  background: rgba(var(--v-theme-info), 0.05) !important;
  border-color: rgba(var(--v-theme-info), 0.12) !important;
}
.card-info:hover {
  background: rgba(var(--v-theme-info), 0.08) !important;
  border-color: rgba(var(--v-theme-info), 0.2) !important;
}

/* Card Warning */
.card-warning {
  background: rgba(var(--v-theme-warning), 0.05) !important;
  border-color: rgba(var(--v-theme-warning), 0.12) !important;
}
.card-warning:hover {
  background: rgba(var(--v-theme-warning), 0.08) !important;
  border-color: rgba(var(--v-theme-warning), 0.2) !important;
}

.stats-panel-skeleton {
  display: inline-block;
  width: 48px;
  height: 14px;
  background: linear-gradient(90deg, rgba(var(--v-theme-on-surface), 0.06) 25%, rgba(var(--v-theme-on-surface), 0.12) 50%, rgba(var(--v-theme-on-surface), 0.06) 75%);
  background-size: 200% 100%;
  animation: loadingShimmer 1.5s infinite;
  border-radius: 3px;
  vertical-align: middle;
}

@keyframes loadingShimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.plugin-sidebar-card {
  display: flex;
  flex-direction: column;
}

.plugin-list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 12px !important;
}

/* Custom modern scrollbar for the plugin list */
.plugin-list-scroll::-webkit-scrollbar {
  width: 4px;
}

.plugin-list-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.plugin-list-scroll::-webkit-scrollbar-thumb {
  background: rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
}

.plugin-list-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(var(--v-theme-on-surface), 0.24);
}

.sort-menu-btn {
  letter-spacing: normal !important;
}

.width-100 {
  width: 100%;
}

.gap-1 {
  gap: 4px;
}

.gap-2 {
  gap: 8px;
}

.gap-3 {
  gap: 12px;
}

.cursor-pointer {
  cursor: pointer;
}

.max-width-xl {
  max-width: 1400px;
}
</style>
