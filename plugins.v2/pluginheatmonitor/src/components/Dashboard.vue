<template>
  <div class="heat-monitor-dashboard">
    <!-- 无边框模式 -->
    <v-card v-if="!config?.attrs?.border" flat class="dashboard-card">
      <v-card-text class="pa-0">
        <div class="dashboard-content">
          <!-- 初始加载状态 -->
          <div v-if="initialLoading" class="d-flex justify-center align-center py-8">
            <div class="text-center">
              <v-progress-circular indeterminate color="primary" size="40"></v-progress-circular>
              <div class="text-caption mt-2 text-medium-emphasis">正在加载插件热度数据...</div>
            </div>
          </div>

          <!-- 主要内容 -->
          <div v-else class="dashboard-main">
            <!-- 状态头部 -->
            <div class="status-header mb-4">
              <div class="d-flex align-center justify-space-between">
                <div class="d-flex align-center">
                  <v-avatar size="40" class="mr-3 plugin-logo">
                    <v-img
                      src="https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png"
                      alt="Heat Monitor Logo"
                    >
                      <template v-slot:placeholder>
                        <v-icon color="primary" size="24">mdi-chart-timeline-variant</v-icon>
                      </template>
                    </v-img>
                  </v-avatar>
                  <div>
                    <div class="text-subtitle-2 font-weight-medium">
                      插件热度监控
                      <v-chip
                        v-if="selectedPeriod"
                        color="primary"
                        size="x-small"
                        variant="tonal"
                        class="ml-2"
                      >
                        {{ selectedPeriodText }}
                      </v-chip>
                    </div>
                    <div class="text-caption text-medium-emphasis">{{ statusText }}</div>
                  </div>
                </div>
                <div class="d-flex align-center">
                  <!-- 刷新指示器 -->
                  <v-progress-circular
                    v-if="refreshing"
                    indeterminate
                    color="primary"
                    size="16"
                    width="2"
                    class="mr-2"
                  ></v-progress-circular>
                  <v-chip
                    color="success"
                    size="small"
                    variant="tonal"
                    class="text-caption"
                  >
                    {{ totalDownloads.toLocaleString() }}
                  </v-chip>
                </div>
              </div>
            </div>

            <!-- 三级热力图 -->
            <div class="heatmap-section">
              <HeatmapLevels
                :year-data="yearData"
                :month-data="monthData"
                :day-data="dayData"
                :live-increments="liveIncrements"
                :selected-year="selectedYear"
                :selected-month="selectedMonth"
                @select-year="handleSelectYear"
                @select-month="handleSelectMonth"
              />
            </div>

            <!-- 详细信息 -->
            <div v-if="selectedPeriodData" class="detail-section mt-4">
              <v-card variant="outlined" class="detail-card">
                <v-card-title class="text-subtitle-2 pb-2">
                  {{ selectedPeriodText }}详细数据
                </v-card-title>
                <v-card-text class="pt-0">
                  <div class="detail-content">
                    <div class="d-flex justify-space-between align-center mb-2">
                      <span class="text-body-2">总下载量</span>
                      <v-chip size="small" color="primary" variant="tonal">
                        {{ selectedPeriodData.downloads?.toLocaleString() || 0 }}
                      </v-chip>
                    </div>
                    <div class="d-flex justify-space-between align-center mb-2">
                      <span class="text-body-2">增长量</span>
                      <v-chip 
                        size="small" 
                        :color="selectedPeriodData.growth > 0 ? 'success' : 'grey'"
                        variant="tonal"
                      >
                        +{{ selectedPeriodData.growth?.toLocaleString() || 0 }}
                      </v-chip>
                    </div>
                    <div class="d-flex justify-space-between align-center">
                      <span class="text-body-2">最后更新</span>
                      <span class="text-caption text-medium-emphasis">
                        {{ selectedPeriodData.lastUpdate || '未知' }}
                      </span>
                    </div>
                  </div>
                </v-card-text>
              </v-card>
            </div>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <!-- 带边框模式 -->
    <v-card v-else class="dashboard-card">
      <v-card-item>
        <div class="d-flex align-center justify-space-between">
          <div class="d-flex align-center">
            <v-avatar size="48" class="mr-4 plugin-logo">
              <v-img
                src="https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png"
                alt="Heat Monitor Logo"
              >
                <template v-slot:placeholder>
                  <v-icon color="primary" size="28">mdi-chart-timeline-variant</v-icon>
                </template>
              </v-img>
            </v-avatar>
            <div>
              <div class="d-flex align-center">
                <v-card-title class="text-h6 pa-0">{{ config?.attrs?.title || '插件热度监控' }}</v-card-title>
                <v-chip
                  v-if="selectedPeriod"
                  color="primary"
                  size="small"
                  variant="tonal"
                  class="ml-3"
                >
                  {{ selectedPeriodText }}
                </v-chip>
              </div>
              <v-card-subtitle v-if="config?.attrs?.subtitle" class="pa-0">{{ config.attrs.subtitle }}</v-card-subtitle>
            </div>
          </div>
          <!-- 刷新指示器 -->
          <v-progress-circular
            v-if="refreshing"
            indeterminate
            color="primary"
            size="20"
            width="2"
          ></v-progress-circular>
        </div>
      </v-card-item>

      <v-card-text>
        <!-- 初始加载状态 -->
        <div v-if="initialLoading" class="d-flex justify-center align-center py-8">
          <div class="text-center">
            <v-progress-circular indeterminate color="primary" size="40"></v-progress-circular>
            <div class="text-caption mt-2 text-medium-emphasis">正在加载插件热度数据...</div>
          </div>
        </div>

        <!-- 主要内容 -->
        <div v-else class="dashboard-main">
          <!-- 状态概览 -->
          <div class="status-overview mb-4">
            <v-alert
              type="success"
              variant="tonal"
              density="compact"
              icon="mdi-chart-timeline-variant"
            >
              <div class="d-flex align-center justify-space-between">
                <span>监控 {{ Object.keys(yearData).length }} 个插件，总下载量 {{ totalDownloads.toLocaleString() }}（所有插件累计）</span>
                <v-chip size="small" variant="text">
                  {{ lastUpdateTime }}
                </v-chip>
              </div>
            </v-alert>
          </div>

          <!-- 视图切换按钮 -->
          <div class="view-toggle-section mb-3">
            <div class="d-flex align-center justify-space-between">
              <div class="d-flex align-center">
                <v-icon class="mr-2" color="primary">
                  {{ viewMode === 'heatmap' ? 'mdi-chart-timeline-variant' : 'mdi-chart-line' }}
                </v-icon>
                <span class="text-h6">
                  {{ viewMode === 'heatmap' ? '下载量热力图' : '下载量趋势图' }}
                </span>
              </div>
              <v-btn-toggle
                v-model="viewMode"
                color="primary"
                size="small"
                variant="outlined"
                mandatory
              >
                <v-btn value="heatmap" size="small">
                  <v-icon start>mdi-chart-timeline-variant</v-icon>
                  热力图
                </v-btn>
                <v-btn value="trend" size="small">
                  <v-icon start>mdi-chart-line</v-icon>
                  趋势图
                </v-btn>
              </v-btn-toggle>
            </div>
          </div>

          <!-- 热力图视图 -->
          <div v-if="viewMode === 'heatmap'" class="heatmap-section mb-4">
            <HeatmapLevels
              :year-data="yearData"
              :month-data="monthData"
              :day-data="dayData"
              :live-increments="liveIncrements"
              :selected-year="selectedYear"
              :selected-month="selectedMonth"
              @select-year="handleSelectYear"
              @select-month="handleSelectMonth"
            />
          </div>

          <!-- 趋势图视图 -->
          <div v-else-if="viewMode === 'trend'" class="trend-section mb-4">
            <TrendChart
              :api="api"
              :day-data="dayData"
            />
          </div>

          <!-- 详细信息 -->
          <div v-if="selectedPeriodData" class="detail-section">
            <v-card variant="tonal" class="detail-card">
              <v-card-title class="text-subtitle-2 pb-2">
                <v-icon class="mr-2" size="18">mdi-information-outline</v-icon>
                {{ selectedPeriodText }}详细数据
              </v-card-title>
              <v-card-text class="pt-0">
                <v-row dense>
                  <v-col cols="6" sm="3">
                    <v-card variant="tonal" class="metric-card pa-3" color="primary">
                      <div class="text-center">
                        <v-icon size="24" class="mb-2" color="primary">mdi-download</v-icon>
                        <div class="text-h6 font-weight-bold">
                          {{ selectedPeriodData.downloads?.toLocaleString() || 0 }}
                        </div>
                        <div class="text-caption text-medium-emphasis">总下载量</div>
                      </div>
                    </v-card>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-card variant="tonal" class="metric-card pa-3" color="success">
                      <div class="text-center">
                        <v-icon size="24" class="mb-2" color="success">mdi-trending-up</v-icon>
                        <div class="text-h6 font-weight-bold">
                          +{{ selectedPeriodData.growth?.toLocaleString() || 0 }}
                        </div>
                        <div class="text-caption text-medium-emphasis">增长量</div>
                      </div>
                    </v-card>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-card variant="tonal" class="metric-card pa-3" color="info">
                      <div class="text-center">
                        <v-icon size="24" class="mb-2" color="info">mdi-calendar</v-icon>
                        <div class="text-body-1 font-weight-bold">
                          {{ selectedPeriodData.period || '未知' }}
                        </div>
                        <div class="text-caption text-medium-emphasis">时间段</div>
                      </div>
                    </v-card>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-card variant="tonal" class="metric-card pa-3" color="warning">
                      <div class="text-center">
                        <v-icon size="24" class="mb-2" color="warning">mdi-clock-outline</v-icon>
                        <div class="text-body-2 font-weight-bold">
                          {{ selectedPeriodData.lastUpdate || '未知' }}
                        </div>
                        <div class="text-caption text-medium-emphasis">最后更新</div>
                      </div>
                    </v-card>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import '../styles/tokens.css'
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useDisplay } from 'vuetify'
import HeatmapLevels from './HeatmapLevels.vue'
import TrendChart from './TrendChart.vue'

// 接收仪表板配置
const props = defineProps({
  config: {
    type: Object,
    default: () => ({}),
  },
  allowRefresh: {
    type: Boolean,
    default: true,
  },
  api: {
    type: Object,
    required: true,
  },
})

// 使用Vuetify的响应式断点
const { xs, sm } = useDisplay()

// 从插件配置中获取Dashboard设置
const dashboardConfig = computed(() => {
  const pluginConfig = props.config?.attrs?.pluginConfig || {}
  return {
    refreshInterval: pluginConfig.dashboard_refresh_interval || 30,
    autoRefresh: pluginConfig.dashboard_auto_refresh !== false,
  }
})

// 组件状态
const initialLoading = ref(true)
const refreshing = ref(false)
const lastUpdateTime = ref('')
const viewMode = ref('heatmap') // 'heatmap' 或 'trend'

// 热力图数据
const yearData = reactive({})
const monthData = reactive({})
const dayData = reactive({})
const liveIncrements = reactive({})

// 选择状态
const selectedYear = ref(null)
const selectedMonth = ref(null)
const selectedPeriod = ref(null)

// 统计数据
const totalDownloads = ref(0)

let refreshTimer = null

// 计算属性
const statusText = computed(() => {
  const pluginCount = Object.keys(yearData).length
  if (pluginCount === 0) return '暂无监控插件'
  return `监控 ${pluginCount} 个插件`
})

const selectedPeriodText = computed(() => {
  if (selectedYear.value && selectedMonth.value) {
    return `${selectedYear.value}年${selectedMonth.value.split('-')[1]}月`
  } else if (selectedYear.value) {
    return `${selectedYear.value}年`
  } else if (selectedMonth.value) {
    const [year, month] = selectedMonth.value.split('-')
    return `${year}年${month}月`
  }
  return ''
})

const selectedPeriodData = computed(() => {
  if (!selectedPeriod.value) return null

  // 根据选择的时间段返回相应数据
  if (selectedYear.value && selectedMonth.value) {
    // 月份数据
    const monthKey = selectedMonth.value
    return {
      downloads: monthData[monthKey] || 0,
      growth: calculateGrowth('month', monthKey),
      period: selectedPeriodText.value,
      lastUpdate: lastUpdateTime.value
    }
  } else if (selectedYear.value) {
    // 年份数据
    return {
      downloads: yearData[selectedYear.value] || 0,
      growth: calculateGrowth('year', selectedYear.value),
      period: selectedPeriodText.value,
      lastUpdate: lastUpdateTime.value
    }
  }
  return null
})

// 计算增长量
function calculateGrowth(type, key) {
  // 这里可以实现具体的增长量计算逻辑
  // 暂时返回模拟数据
  return Math.floor(Math.random() * 100)
}

// 处理年份选择
function handleSelectYear(year) {
  selectedYear.value = year
  selectedMonth.value = null
  selectedPeriod.value = 'year'

  // 可以在这里调用API获取指定年份的详细数据
  loadYearData(year)
}

// 处理月份选择
function handleSelectMonth(monthKey) {
  const [year, month] = monthKey.split('-')
  selectedYear.value = parseInt(year)
  selectedMonth.value = monthKey
  selectedPeriod.value = 'month'

  // 可以在这里调用API获取指定月份的详细数据
  loadMonthData(monthKey)
}

// 加载年份数据
async function loadYearData(year) {
  try {
    const data = await props.api.get(`plugin/PluginHeatMonitor/year-data/${year}`)
    if (data) {
      // 更新年份相关的月份和日期数据
      Object.assign(monthData, data.monthData || {})
      Object.assign(dayData, data.dayData || {})
    }
  } catch (error) {
    console.error('加载年份数据失败:', error)
  }
}

// 加载月份数据
async function loadMonthData(monthKey) {
  try {
    const data = await props.api.get(`plugin/PluginHeatMonitor/month-data/${monthKey}`)
    if (data) {
      // 更新月份相关的日期数据
      Object.assign(dayData, data.dayData || {})
    }
  } catch (error) {
    console.error('加载月份数据失败:', error)
  }
}

// 获取仪表板数据
async function fetchDashboardData(isInitial = false) {
  if (!props.allowRefresh) return

  // 设置加载状态
  if (isInitial) {
    initialLoading.value = true
  } else {
    refreshing.value = true
  }

  try {
    // 获取热力图数据
    const heatmapData = await props.api.get('plugin/PluginHeatMonitor/heatmap-data')

    // 获取仪表板数据（包含真实的总下载量）
    const dashboardData = await props.api.get('plugin/PluginHeatMonitor/data')

    if (heatmapData) {
      // 更新热力图数据
      Object.assign(yearData, heatmapData.yearData || {})
      Object.assign(monthData, heatmapData.monthData || {})
      Object.assign(dayData, heatmapData.dayData || {})
    }

    if (dashboardData && dashboardData.status === 'success') {
      // 使用真实的总下载量（所有插件的当前下载量之和）
      totalDownloads.value = dashboardData.total_downloads || 0

      // 计算今日的实际增长量总和（从daily_downloads获取）
      const today = new Date().toISOString().split('T')[0]
      const todayTotalGrowth = dashboardData.plugins?.reduce((sum, plugin) => {
        // 从每日下载数据中获取今日增长量
        const dailyDownloads = plugin.daily_downloads || {}
        const todayData = dailyDownloads[today]
        if (todayData && !todayData.is_historical) {
          return sum + (todayData.value || todayData || 0)
        }
        return sum
      }, 0) || 0

      // 更新实时增量数据
      Object.assign(liveIncrements, { [today]: todayTotalGrowth })
    } else {
      // 如果无法获取仪表板数据，回退到热力图数据计算
      totalDownloads.value = Object.values(yearData).reduce((sum, val) => sum + val, 0)
    }

    // 更新最后更新时间
    lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })

  } catch (error) {
    console.error('获取仪表板数据失败:', error)
  } finally {
    // 清除加载状态
    initialLoading.value = false
    refreshing.value = false
  }
}

// 设置定时刷新
function setupRefreshTimer() {
  if (props.allowRefresh && dashboardConfig.value.autoRefresh) {
    const intervalMs = dashboardConfig.value.refreshInterval * 1000

    refreshTimer = setInterval(() => {
      fetchDashboardData(false)
    }, intervalMs)
  }
}

// 初始化
onMounted(() => {
  setTimeout(() => {
    fetchDashboardData(true)
    setupRefreshTimer()
  }, 100)
})

// 清理
onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.heat-monitor-dashboard {
  width: 100%;
  height: 100%;
}

.dashboard-card {
  height: 100%;
  transition: var(--heat-transition);
}

.dashboard-content {
  height: 100%;
}

.dashboard-main {
  animation: heatScaleIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.status-header {
  padding: 12px 16px;
  background: rgba(var(--v-theme-surface-variant), 0.05);
  border-radius: 8px;
  border: 1px solid var(--heat-border);
}

.detail-card {
  background: rgba(var(--v-theme-surface), 0.4) !important;
  backdrop-filter: blur(12px);
  border: 1px solid var(--heat-border) !important;
  border-radius: 12px !important;
  transition: var(--heat-transition) !important;
}

.detail-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.3) !important;
  box-shadow: var(--heat-shadow-md) !important;
}

/* 插件Logo样式 */
.plugin-logo {
  background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
  border: 2px solid rgba(var(--v-theme-primary), 0.2);
  box-shadow: var(--heat-shadow-sm);
  transition: var(--heat-transition);
}

.v-theme--dark .plugin-logo {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-color: rgba(var(--v-theme-primary), 0.3);
}

.plugin-logo:hover {
  transform: scale(1.05);
  border-color: rgba(var(--v-theme-primary), 0.4);
  box-shadow: var(--heat-shadow-md);
}

.plugin-logo .v-img {
  border-radius: inherit;
}

/* 指标卡片样式 */
.metric-card {
  background: rgba(var(--v-theme-surface), 0.4) !important;
  border: 1px solid var(--heat-border) !important;
  transition: var(--heat-transition) !important;
  border-radius: 12px !important;
  overflow: hidden;
  position: relative;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--heat-shadow-md) !important;
  border-color: currentColor !important;
}

.metric-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, currentColor 0%, transparent 100%);
  opacity: 0.6;
}

/* 视图切换样式 */
.view-toggle-section {
  border-bottom: 1px solid var(--heat-border);
  padding-bottom: 12px;
}

/* 响应式设计 */
@media (max-width: 600px) {
  .status-header {
    padding: 8px 12px;
  }

  .dashboard-main {
    padding: 0 4px;
  }

  .view-toggle-section .d-flex {
    flex-direction: column;
    align-items: flex-start !important;
    gap: 12px;
  }

  .view-toggle-section .d-flex:last-child {
    align-items: center !important;
    width: 100%;
    justify-content: center;
  }
}

/* 加载动画优化 */
.v-progress-circular {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.7; }
  100% { opacity: 1; }
}

/* 状态指示器动画 */
.v-chip {
  transition: var(--heat-transition);
}

.v-chip:hover {
  transform: scale(1.05);
}

/* 头像动画 */
.v-avatar {
  transition: var(--heat-transition);
}

.v-avatar:hover {
  transform: scale(1.1);
  box-shadow: 0 2px 8px rgba(var(--v-theme-primary), 0.3);
}
</style>
