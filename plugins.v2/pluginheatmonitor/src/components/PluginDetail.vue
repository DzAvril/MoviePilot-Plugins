<template>
  <v-card
    class="plugin-detail-card overflow-hidden"
    :class="[flat ? 'elevation-0 bg-transparent border-0 pa-0' : 'heat-glass-card']"
    :style="flat ? 'background: transparent !important;' : ''"
    variant="flat"
  >
    <!-- Header -->
    <div :class="[flat ? 'py-1 px-0' : 'pa-2 pa-sm-4 pb-2']">
      <div class="d-flex align-center justify-space-between width-100">
        <div class="d-flex align-center gap-2">
          <!-- Icon -->
          <v-icon color="primary" size="24">
            {{ viewMode === 'heatmap' ? 'mdi-calendar-month-outline' : 'mdi-chart-line' }}
          </v-icon>
          <!-- Title -->
          <span class="text-subtitle-1 font-weight-bold text-high-emphasis">
            {{ viewMode === 'heatmap' ? '全局热度日历' : '下载增量趋势' }}
          </span>
          <!-- Year or Time Range selector chip -->
          <!-- For Heatmap mode: selectedYear -->
          <v-menu v-if="viewMode === 'heatmap'" location="bottom start" offset="5">
            <template v-slot:activator="{ props }">
              <v-chip
                v-bind="props"
                size="small"
                class="custom-purple-chip font-weight-bold cursor-pointer"
              >
                {{ selectedYear }}
              </v-chip>
            </template>
            <v-list density="compact">
              <v-list-item
                v-for="year in availableYears"
                :key="year"
                @click="selectedYear = year"
                :active="selectedYear === year"
                color="primary"
              >
                <v-list-item-title class="text-caption font-weight-medium">{{ year }}年</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
          <!-- For Trend mode: timeRange -->
          <v-menu v-else location="bottom start" offset="5">
            <template v-slot:activator="{ props }">
              <v-chip
                v-bind="props"
                size="small"
                class="custom-purple-chip font-weight-bold cursor-pointer"
              >
                {{ timeRange === 'all' ? '全部' : timeRange + '天' }}
              </v-chip>
            </template>
            <v-list density="compact">
              <v-list-item
                v-for="opt in [{title:'30天', value:'30'}, {title:'90天', value:'90'}, {title:'全部', value:'all'}]"
                :key="opt.value"
                @click="timeRange = opt.value"
                :active="timeRange === opt.value"
                color="primary"
              >
                <v-list-item-title class="text-caption font-weight-medium">{{ opt.title }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
        </div>

        <!-- View Mode Toggle on the right -->
        <!-- Mobile: icon-only grouped buttons styled like Page topbar -->
        <v-btn-group v-if="$vuetify.display.xs" variant="tonal" density="compact" class="elevation-0">
          <v-btn
            color="primary"
            size="small"
            min-width="40"
            class="px-0"
            @click="viewMode = 'heatmap'"
          >
            <v-icon size="18">mdi-pulse</v-icon>
          </v-btn>
          <v-btn
            color="primary"
            size="small"
            min-width="40"
            class="px-0"
            @click="viewMode = 'trend'"
          >
            <v-icon size="18">mdi-chart-line</v-icon>
          </v-btn>
        </v-btn-group>
        <!-- Desktop: icon+text toggle with active state -->
        <div v-else class="d-flex align-center gap-1">
          <v-btn
            :variant="viewMode === 'heatmap' ? 'tonal' : 'text'"
            :color="viewMode === 'heatmap' ? 'primary' : 'default'"
            size="small"
            density="compact"
            prepend-icon="mdi-pulse"
            class="view-mode-btn"
            @click="viewMode = 'heatmap'"
          >
            热度日历
          </v-btn>
          <v-btn
            :variant="viewMode === 'trend' ? 'tonal' : 'text'"
            :color="viewMode === 'trend' ? 'primary' : 'default'"
            size="small"
            density="compact"
            prepend-icon="mdi-chart-line"
            class="view-mode-btn"
            @click="viewMode = 'trend'"
          >
            增量趋势
          </v-btn>
        </div>
      </div>
    </div>

    <v-card-text :class="[flat ? 'pa-0 pt-2' : 'pa-2 pa-sm-4 pt-0 main-chart-card-text']">
      <div v-if="loading" class="d-flex justify-center align-center py-12">
        <v-progress-circular indeterminate color="primary" size="40"></v-progress-circular>
        <span class="text-body-2 text-medium-emphasis ml-3">正在加载分析数据...</span>
      </div>

      <div v-else class="detail-container">
        <!-- Row 2: Plugin Banner -->
        <div class="d-flex align-center justify-space-between py-1 mb-2">
          <div class="d-flex align-center">
            <!-- Real Plugin Icon/Avatar -->
            <v-avatar size="44" class="mr-3" style="border: 1px solid rgba(0,0,0,0.06); background: white;">
              <v-img :src="plugin.icon || plugin.plugin_icon || pluginDetailData?.plugin_icon" v-if="plugin.icon || plugin.plugin_icon || pluginDetailData?.plugin_icon">
                <template v-slot:placeholder>
                  <v-icon size="24" color="primary">mdi-puzzle-outline</v-icon>
                </template>
              </v-img>
              <v-icon v-else size="24" color="primary">mdi-puzzle-outline</v-icon>
            </v-avatar>

            <!-- Name & Subtitle -->
            <div class="d-flex flex-column">
              <div class="d-flex align-center gap-1">
                <span class="text-subtitle-1 font-weight-bold text-high-emphasis" style="line-height: 1.25;">
                  {{ plugin.plugin_name || plugin.name }}
                </span>
                <span class="text-caption text-medium-emphasis" style="opacity: 0.6;">({{ plugin.plugin_id || plugin.id }})</span>
              </div>
              <span class="text-caption text-medium-emphasis mt-1">
                {{ (pluginDetailData?.current_downloads || plugin.downloads || 0).toLocaleString() }} downloads in {{ selectedYear }}
              </span>
            </div>
          </div>

          <!-- Reset Button -->
          <v-btn
            size="small"
            color="warning"
            variant="outlined"
            prepend-icon="mdi-refresh"
            @click="showResetConfirm = true"
            :loading="resetting"
            class="custom-reset-btn d-none d-sm-flex"
          >
            重置数据
          </v-btn>
        </div>

        <!-- Top: Statistical Row -->
        <div class="stats-grid">
          <div class="stats-card pa-2 text-center">
            <div class="stats-value text-success">{{ (pluginDetailData?.current_downloads || plugin.downloads || 0).toLocaleString() }}</div>
            <div class="stats-label">总下载量</div>
          </div>

          <div class="stats-card pa-2 text-center">
            <div class="stats-value text-primary">{{ activeDays }}</div>
            <div class="stats-label">活跃天数</div>
          </div>

          <div class="stats-card pa-2 text-center">
            <div class="stats-value text-warning">+{{ maxDayIncrement }}</div>
            <div class="stats-label">最高单日新增</div>
          </div>

          <div class="stats-card pa-2 text-center">
            <div class="stats-value text-info">{{ currentStreak }} 天</div>
            <div class="stats-label">连续增长天数</div>
          </div>
        </div>

        <!-- Bottom: Visualization (Heatmap or Trend Chart) -->
        <div class="vis-section">
          <!-- Heatmap View -->
          <div v-if="viewMode === 'heatmap'" class="heatmap-view-container position-relative">
            <GitHubHeatmap
              :api="api"
              :selected-plugin-id="plugin.plugin_id || plugin.id"
              v-model:selected-year="selectedYear"
              :hide-stats="true"
              :hide-header="true"
              class="heatmap-fill"
              ref="heatmapRef"
            />
          </div>

          <!-- Trend Chart View -->
          <div v-else-if="viewMode === 'trend'" class="trend-view-container">
            <TrendChart
              :api="api"
              :plugin-data="pluginDetailData"
              :time-range="timeRange"
              :hide-filter="true"
              ref="trendChartRef"
            />
          </div>
        </div>
      </div>
    </v-card-text>

    <!-- Tooltip -->
    <teleport to="body">
      <div
        v-if="tooltip.show"
        class="heatmap-tooltip"
        :style="tooltip.style"
      >
        {{ tooltip.content }}
      </div>
    </teleport>

    <!-- Reset Dialog -->
    <v-dialog v-model="showResetConfirm" max-width="400">
      <v-card class="heat-glass-card">
        <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center">
          <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
          确认要重置该插件数据吗？
        </v-card-title>
        <v-card-text class="text-body-2 pt-2">
          此操作将清空插件「{{ plugin.plugin_name }}」的所有每日监控记录，以当前下载量作为新的计算基准。此操作不可逆。
        </v-card-text>
        <v-card-actions class="pa-3">
          <v-spacer></v-spacer>
          <v-btn size="small" variant="outlined" @click="showResetConfirm = false">取消</v-btn>
          <v-btn size="small" color="error" variant="flat" @click="resetPluginData" :loading="resetting">确认重置</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import TrendChart from './TrendChart.vue'
import GitHubHeatmap from './GitHubHeatmap.vue'

const props = defineProps({
  plugin: {
    type: Object,
    required: true
  },
  api: {
    type: Object,
    required: true
  },
  flat: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['data-changed'])

const loading = ref(true)
const resetting = ref(false)
const showResetConfirm = ref(false)
const viewMode = ref('heatmap')
const timeRange = ref('30')
const selectedYear = ref(new Date().getFullYear())
const availableYears = ref([new Date().getFullYear()])
const pluginDetailData = ref(null)
const windowWidth = ref(window.innerWidth)

// Tooltip state
const tooltip = reactive({
  show: false,
  content: '',
  style: {}
})

function handleResize() {
  windowWidth.value = window.innerWidth
}

// Helper methods for formatting
function getDayValue(dayData) {
  if (typeof dayData === 'object' && dayData !== null) {
    return dayData.value || 0
  }
  return dayData || 0
}

function isHistoricalData(dayData) {
  if (typeof dayData === 'object' && dayData !== null) {
    return dayData.is_historical || false
  }
  return false
}

function isOutlierData(dayData) {
  if (typeof dayData === 'object' && dayData !== null) {
    return dayData.is_outlier || false
  }
  return false
}

// Fetch plugin detail data
async function loadDetailData() {
  loading.value = true
  try {
    const response = await props.api.get(`plugin/PluginHeatMonitor/plugin-heatmap?plugin_id=${props.plugin.plugin_id || props.plugin.id}`)
    if (response && response.status === 'success') {
      pluginDetailData.value = {
        plugin_id: props.plugin.plugin_id || props.plugin.id,
        plugin_name: props.plugin.plugin_name || props.plugin.name,
        plugin_icon: props.plugin.plugin_icon || props.plugin.icon,
        daily_downloads: response.dayData || response.daily_downloads || {},
        current_downloads: response.current_downloads || props.plugin.downloads || 0
      }

      // Extract available years from daily downloads keys
      const years = new Set()
      Object.keys(pluginDetailData.value.daily_downloads).forEach(dateStr => {
        const yr = new Date(dateStr).getFullYear()
        if (!isNaN(yr)) years.add(yr)
      })
      if (years.size > 0) {
        availableYears.value = Array.from(years).sort((a, b) => b - a)
      } else {
        availableYears.value = [new Date().getFullYear()]
      }
      
      if (!availableYears.value.includes(selectedYear.value)) {
        selectedYear.value = availableYears.value[0]
      }
    }
  } catch (error) {
    console.error('加载插件详情数据失败:', error)
  } finally {
    loading.value = false
  }
}

// Reset data
async function resetPluginData() {
  resetting.value = true
  try {
    const pId = props.plugin.plugin_id || props.plugin.id
    const response = await props.api.post('plugin/PluginHeatMonitor/reset-plugin-heatmap', {
      plugin_id: pId
    })
    if (response && response.status === 'success') {
      showResetConfirm.value = false
      await loadDetailData()
      emit('data-changed')
    }
  } catch (error) {
    console.error('重置数据失败:', error)
  } finally {
    resetting.value = false
  }
}

// Compute statistics
const activeDays = computed(() => {
  if (!pluginDetailData.value?.daily_downloads) return 0
  return Object.entries(pluginDetailData.value.daily_downloads)
    .filter(([date, val]) => {
      const yr = new Date(date).getFullYear()
      const dVal = getDayValue(val)
      return yr === selectedYear.value && dVal > 0 && !isHistoricalData(val) && !isOutlierData(val)
    }).length
})

const maxDayIncrement = computed(() => {
  if (!pluginDetailData.value?.daily_downloads) return 0
  const values = Object.entries(pluginDetailData.value.daily_downloads)
    .filter(([date, val]) => {
      const yr = new Date(date).getFullYear()
      return yr === selectedYear.value && !isHistoricalData(val) && !isOutlierData(val)
    })
    .map(([, val]) => getDayValue(val))
  return values.length > 0 ? Math.max(...values) : 0
})

const currentStreak = computed(() => {
  if (!pluginDetailData.value?.daily_downloads) return 0
  const today = new Date()
  let streak = 0
  let curr = new Date(today)
  
  while (curr.getFullYear() === selectedYear.value) {
    const dStr = curr.getFullYear() + '-' +
                 String(curr.getMonth() + 1).padStart(2, '0') + '-' +
                 String(curr.getDate()).padStart(2, '0')
    const item = pluginDetailData.value.daily_downloads[dStr]
    if (item && getDayValue(item) > 0 && !isHistoricalData(item) && !isOutlierData(item)) {
      streak++
    } else {
      break
    }
    curr.setDate(curr.getDate() - 1)
  }
  return streak
})

// Generate heatmap squares for selected year
const heatmapSquares = computed(() => {
  if (!pluginDetailData.value?.daily_downloads) return []
  
  const squares = []
  const startDate = new Date(selectedYear.value, 0, 1)
  const firstSunday = new Date(startDate)
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() - 1)
  }
  
  const current = new Date(firstSunday)
  const dailyDownloads = pluginDetailData.value.daily_downloads
  
  // Find max value for scaling color level
  const normalValues = Object.values(dailyDownloads)
    .filter(val => getDayValue(val) > 0 && !isHistoricalData(val) && !isOutlierData(val))
    .map(val => getDayValue(val))
  const maxValue = Math.max(...(normalValues.length > 0 ? normalValues : [1]), 1)
  
  for (let week = 0; week < 53; week++) {
    for (let day = 0; day < 7; day++) {
      const dateStr = current.getFullYear() + '-' +
                      String(current.getMonth() + 1).padStart(2, '0') + '-' +
                      String(current.getDate()).padStart(2, '0')
      
      const dayData = dailyDownloads[dateStr]
      const value = getDayValue(dayData)
      const isHist = isHistoricalData(dayData)
      const isOut = isOutlierData(dayData)
      
      let level = 0
      if (value > 0) {
        if (isHist || isOut) {
          level = Math.min(2, Math.ceil((value / maxValue) * 2))
        } else {
          level = Math.min(4, Math.ceil((value / maxValue) * 4))
        }
      }
      
      squares.push({
        date: new Date(current),
        dateStr,
        value,
        level,
        week,
        day,
        isInYear: current.getFullYear() === selectedYear.value,
        isHistorical: isHist,
        isOutlier: isOut
      })
      
      current.setDate(current.getDate() + 1)
    }
  }
  return squares
})

// Month labels positions
const monthLabels = computed(() => {
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  let sqSize = 13
  let gap = 2
  
  if (windowWidth.value <= 768) {
    sqSize = 10
  }
  
  const columnWidth = sqSize + gap
  const labels = []
  const seenMonths = new Set()
  
  const startDate = new Date(selectedYear.value, 0, 1)
  const firstSunday = new Date(startDate)
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() - 1)
  }
  
  for (let w = 0; w < 53; w++) {
    const currentSunday = new Date(firstSunday)
    currentSunday.setDate(firstSunday.getDate() + w * 7)
    
    let monthIdx = currentSunday.getMonth()
    if (currentSunday.getFullYear() < selectedYear.value) {
      monthIdx = 0
    }
    
    if (!seenMonths.has(monthIdx) && (currentSunday.getFullYear() === selectedYear.value || w === 0)) {
      seenMonths.add(monthIdx)
      labels.push({
        name: monthNames[monthIdx],
        position: w * columnWidth
      })
    }
  }
  return labels
})

// Tooltip interaction
function getSquareClass(sq) {
  let cls = `github-level-${sq.level}`
  if (!sq.isInYear) cls += ' opacity-30'
  if (sq.isHistorical) cls += ' historical-box'
  if (sq.isOutlier) cls += ' outlier-box'
  return cls
}

function showTooltip(event, sq) {
  const dateStr = sq.date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
  
  const valStr = sq.value.toLocaleString()
  if (sq.isHistorical) {
    tooltip.content = `${valStr} 历史下载量 on ${dateStr}`
  } else if (sq.isOutlier) {
    tooltip.content = `${valStr} 异常值 (已排除) on ${dateStr}`
  } else {
    tooltip.content = `${valStr} 新增下载 on ${dateStr}`
  }
  
  const mouseX = event.clientX
  const mouseY = event.clientY
  const viewportWidth = window.innerWidth
  const tooltipOffset = 12
  const estimatedWidth = Math.max(120, tooltip.content.length * 8)
  const estimatedHeight = 32

  let left = mouseX
  let top = mouseY - tooltipOffset - estimatedHeight
  let transform = 'translateX(-50%)'

  // Boundary checks
  if (left + estimatedWidth / 2 > viewportWidth - 10) {
    left = mouseX - 10
    transform = 'translateX(-100%)'
  } else if (left - estimatedWidth / 2 < 10) {
    left = mouseX + 10
    transform = 'translateX(0)'
  }

  if (top < 10) {
    top = mouseY + tooltipOffset
  }
  
  tooltip.style = {
    position: 'fixed',
    left: left + 'px',
    top: top + 'px',
    transform: transform,
    zIndex: 1100
  }
  tooltip.show = true
}

function hideTooltip() {
  tooltip.show = false
}

function onSquareClick(sq) {
  // Emit click
}

// Watchers
watch(() => props.plugin, () => {
  loadDetailData()
}, { deep: true })

onMounted(() => {
  loadDetailData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

defineExpose({
  loadDetailData
})
</script>

<style scoped>
.plugin-detail-card {
  box-shadow: none !important;
}

.plugin-detail-card:not(.elevation-0) {
  margin: 0 !important;
  padding: 0 !important;
}

.plugin-detail-card:hover {
  transform: none !important;
  box-shadow: none !important;
  cursor: default;
}

.detail-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.stats-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-surface-variant), 0.03);
  border-radius: 8px;
  transition: var(--heat-transition);
  padding: 6px 4px !important;
}

.stats-card:hover {
  transform: none !important;
  background: rgba(var(--v-theme-surface-variant), 0.06);
  border-color: rgb(var(--v-theme-primary));
}

.stats-value {
  font-size: 14px !important;
  font-weight: 700;
  line-height: 1.2;
}

.stats-label {
  font-size: 9px !important;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 2px;
}

@media (max-width: 480px) {
  .stats-grid {
    gap: 4px;
  }

  .stats-value {
    font-size: 11px !important;
  }

  .stats-label {
    font-size: 8px !important;
  }

  .stats-card {
    padding: 4px 2px !important;
  }
}

/* Compact Toggle Button Styling */
.compact-toggle {
  height: 30px !important;
  border-radius: 6px !important;
}

.compact-toggle :deep(.v-btn) {
  height: 28px !important;
  min-height: 28px !important;
  font-size: 11px !important;
  padding: 0 10px !important;
  min-width: unset !important;
}

.compact-toggle :deep(.v-btn__content) {
  font-size: 11px !important;
}

.compact-toggle :deep(.v-icon) {
  font-size: 14px !important;
  margin-inline-start: 0 !important;
  margin-inline-end: 4px !important;
}

.plugin-avatar {
  border: 2px solid rgba(var(--v-theme-primary), 0.15);
  background: white;
}

.border-b {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
}

.border-t {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
}

.gap-2 {
  gap: 8px;
}

.gap-3 {
  gap: 12px;
}

.gap-1 {
  gap: 4px;
}

/* Heatmap rendering custom */
.heatmap-view-container {
  overflow: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.trend-view-container {
  overflow: hidden;
}

.vis-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.heatmap-fill {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* On mobile, card height is auto — don't let vis-section flex-expand */
@media (max-width: 1279px) {
  .vis-section {
    flex: 0 0 auto;
  }

  .heatmap-view-container {
    flex: 0 0 auto;
  }

  .heatmap-fill {
    flex: 0 0 auto;
  }
}

.month-labels-container {
  position: relative;
  height: 14px;
  margin-bottom: 4px;
}

.month-lbl {
  position: absolute;
  font-size: 10px;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}

.wkday-labels {
  width: 28px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 18px; /* 14px height + 4px margin-bottom of month labels */
}

.wkday-lbl {
  height: 13px;
  line-height: 13px;
  font-size: 10px;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
  text-align: right;
}

@media (max-width: 768px) {
  .wkday-lbl {
    height: 10px;
    line-height: 10px;
  }
}

.heatmap-grid-scroll {
  overflow-x: auto;
  flex-grow: 1;
}

.hm-grid {
  display: grid;
  grid-template-columns: repeat(53, 13px);
  grid-template-rows: repeat(7, 13px);
  gap: 2px;
  grid-auto-flow: column;
}

@media (max-width: 768px) {
  .hm-grid {
    grid-template-columns: repeat(53, 10px);
    grid-template-rows: repeat(7, 10px);
  }
}

.hm-square {
  width: 100%;
  height: 100%;
  border-radius: 2px;
  cursor: pointer;
  outline: 1px solid rgba(27, 31, 35, 0.05);
}

.opacity-30 {
  opacity: 0.3;
}

/* Color classes using custom tokens */
.github-level-0 { background-color: var(--heat-level-0); }
.github-level-1 { background-color: var(--heat-level-1); }
.github-level-2 { background-color: var(--heat-level-2); }
.github-level-3 { background-color: var(--heat-level-3); }
.github-level-4 { background-color: var(--heat-level-4); }

.historical-box {
  border: 1.5px solid var(--heat-warning) !important;
}

.outlier-box {
  border: 1.5px dashed var(--heat-danger) !important;
}

.legend-sq {
  width: 10px;
  height: 10px;
  border-radius: 1px;
}

/* Custom Tooltip已移至全局 styles/tokens.css 中定义，以支持 Teleport 渲染与主题色适配 */

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

.detail-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  overflow-y: auto;
}

.width-100 {
  width: 100%;
}

.view-mode-btn {
  font-size: 12px !important;
  font-weight: 600 !important;
  text-transform: none !important;
  letter-spacing: normal !important;
  border-radius: 6px !important;
  height: 30px !important;
  min-height: 30px !important;
  padding: 0 10px !important;
}

.custom-purple-chip {
  background-color: rgba(var(--v-theme-primary), 0.1) !important;
  color: rgb(var(--v-theme-primary)) !important;
  font-size: 11px !important;
  height: 22px !important;
  border: none !important;
  padding: 0 8px !important;
  border-radius: 12px !important;
}

.custom-reset-btn {
  border-color: #ffb300 !important;
  color: #ffb300 !important;
  font-weight: 600 !important;
  font-size: 12px !important;
  height: 32px !important;
  border-radius: 6px !important;
  text-transform: none !important;
}

.custom-reset-btn :deep(.v-btn__overlay) {
  display: none !important;
}

.custom-reset-btn:hover {
  background-color: rgba(255, 179, 0, 0.06) !important;
}
</style>
