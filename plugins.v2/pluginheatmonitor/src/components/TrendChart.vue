<template>
  <div class="trend-chart">
    <div v-if="!hideFilter" class="chart-header mb-3">
      <div class="d-flex align-center justify-end">
        <v-btn-toggle
          v-model="localTimeRange"
          color="primary"
          size="small"
          variant="outlined"
          mandatory
          density="compact"
          class="trend-time-toggle"
        >
          <v-btn value="30" size="small" class="trend-toggle-btn">30天</v-btn>
          <v-btn value="90" size="small" class="trend-toggle-btn">90天</v-btn>
          <v-btn value="all" size="small" class="trend-toggle-btn">全部</v-btn>
        </v-btn-toggle>
      </div>
    </div>

    <div class="chart-container">
      <v-card variant="flat" class="bg-transparent border-0 elevation-0" style="background: transparent !important;">
        <v-card-text class="pa-0">
          <div v-if="loading" class="text-center py-8">
            <v-progress-circular indeterminate color="primary"></v-progress-circular>
            <div class="mt-2 text-body-2">加载趋势数据...</div>
          </div>

          <div v-else-if="!hasData" class="text-center py-8">
            <v-icon size="48" color="grey-lighten-1">mdi-chart-line-variant</v-icon>
            <div class="mt-2 text-body-1">暂无趋势数据</div>
            <div class="text-body-2 text-medium-emphasis">开始监控插件后将显示下载量趋势</div>
          </div>

          <div v-else class="chart-section">
            <div class="echart-wrapper" :style="{ height: chartHeight + 'px' }">
              <div ref="chartRef" style="width: 100%; height: 100%;"></div>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useTheme } from 'vuetify'
import * as echarts from 'echarts'

const props = defineProps({
  api: {
    type: Object,
    required: true
  },
  // 单插件模式的数据
  pluginData: {
    type: Object,
    default: null
  },
  // 多插件模式的数据
  allPluginsData: {
    type: Array,
    default: () => []
  },
  // 全局日数据（用于Dashboard）
  dayData: {
    type: Object,
    default: () => ({})
  },
  timeRange: {
    type: String,
    default: '30'
  },
  hideFilter: {
    type: Boolean,
    default: false
  }
})

const theme = useTheme()
const isDark = computed(() => {
  // MoviePilot 可能会在 html element 设置 data-theme
  return document.documentElement.getAttribute('data-theme') === 'dark' || theme.global.name.value === 'dark'
})

// 状态
const loading = ref(false)
const localTimeRange = ref(props.timeRange)
const chartRef = ref(null)
let chartInstance = null

watch(() => props.timeRange, (newVal) => {
  localTimeRange.value = newVal
})

// 响应式图表高度
 const chartHeight = ref(240)

const updateChartHeight = () => {
  const width = window.innerWidth
  if (width < 600) {
    chartHeight.value = 180
  } else if (width < 960) {
    chartHeight.value = 210
  } else {
    chartHeight.value = 240
  }
  if (chartInstance) {
    chartInstance.resize()
  }
}

// 计算属性
const hasData = computed(() => {
  if (props.pluginData) {
    // 单插件模式
    return Object.keys(props.pluginData.daily_downloads || {}).length > 0
  } else if (props.allPluginsData.length > 0) {
    // 多插件模式
    return props.allPluginsData.some(plugin =>
      Object.keys(plugin.daily_downloads || {}).length > 0
    )
  } else if (Object.keys(props.dayData).length > 0) {
    // Dashboard模式
    return true
  }
  return false
})



// 辅助函数：处理新旧数据格式
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

// 处理单个插件数据
function processPluginData(plugin) {
  const dailyDownloads = plugin.daily_downloads || {}
  const chartData = []

  // 获取所有日期并排序
  const dates = Object.keys(dailyDownloads).sort()

  dates.forEach(date => {
    const dayData = dailyDownloads[date]
    const value = getDayValue(dayData)
    const isHistorical = isHistoricalData(dayData)

    // 只显示非历史数据，或者如果没有非历史数据则显示所有数据
    if (value > 0 && !isHistorical) {
      chartData.push({
        date: date,
        value: value,
        isHistorical: isHistorical
      })
    }
  })

  // 如果没有非历史数据，则包含历史数据
  if (chartData.length === 0) {
    dates.forEach(date => {
      const dayData = dailyDownloads[date]
      const value = getDayValue(dayData)

      if (value > 0) {
        chartData.push({
          date: date,
          value: value,
          isHistorical: isHistoricalData(dayData)
        })
      }
    })
  }

  return { chartData, dateRange: dates }
}

// 处理全局日数据
function processDayData(dayData) {
  const chartData = []
  
  // 获取所有日期并排序
  const dates = Object.keys(dayData).sort()
  
  dates.forEach(date => {
    const value = dayData[date] || 0
    if (value > 0) {
      chartData.push({
        date: date,
        value: value
      })
    }
  })
  
  return { chartData }
}

// 统一色阶调色盘 (符合 tokens.css 风格)
const CHART_COLORS = [
  '#3b82f6', // 经典蓝
  '#10b981', // 增长绿
  '#f59e0b', // 橙黄
  '#ef4444', // 警示红
  '#8b5cf6', // 优雅紫
  '#ec4899', // 玫瑰粉
  '#06b6d4'  // 青蓝
]

// 渲染 ECharts 图表
const renderChart = async () => {
  await nextTick()
  if (!chartRef.value || !hasData.value) {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    return
  }

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const series = []
  try {
    if (props.pluginData) {
      // 单插件模式
      const { chartData } = processPluginData(props.pluginData)
      if (chartData.length > 0) {
        series.push({
          name: props.pluginData.plugin_name || '插件下载量',
          data: chartData.map(item => [new Date(item.date).getTime(), item.value])
        })
      }
    } else if (props.allPluginsData.length > 0) {
      // 多插件模式
      props.allPluginsData.forEach((plugin, index) => {
        const { chartData } = processPluginData(plugin)
        if (chartData.length > 0) {
          series.push({
            name: plugin.plugin_name || `插件${index + 1}`,
            data: chartData.map(item => [new Date(item.date).getTime(), item.value])
          })
        }
      })
    } else if (Object.keys(props.dayData).length > 0) {
      // Dashboard模式 - 全局日数据
      const { chartData } = processDayData(props.dayData)
      if (chartData.length > 0) {
        series.push({
          name: '全局下载量',
          data: chartData.map(item => [new Date(item.date).getTime(), item.value])
        })
      }
    }

    // 时间范围过滤
    if (localTimeRange.value !== 'all' && series.length > 0) {
      const days = parseInt(localTimeRange.value)
      const cutoffTime = new Date().getTime() - days * 24 * 60 * 60 * 1000
      series.forEach(s => {
        s.data = s.data.filter(point => point[0] >= cutoffTime)
      })
    }
  } catch (error) {
    console.error('❌ ECharts 数据序列构建失败:', error)
  }

  // 根据当前暗色/亮色主题设定色彩配置
  const dark = isDark.value
  const labelColor = dark ? '#94a3b8' : '#64748b'
  const splitLineColor = dark ? '#1e293b' : '#f1f5f9'
  const axisLineColor = dark ? '#334155' : '#cbd5e1'

  const seriesList = series.map((s, index) => ({
    name: s.name,
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    showSymbol: false,
    lineStyle: { width: 3 },
    itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length] },
    data: s.data
  }))

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      backgroundColor: dark ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)',
      borderColor: dark ? '#334155' : '#e5e7eb',
      textStyle: { color: dark ? '#f3f4f6' : '#1f2937', fontSize: 12 },
      padding: 10,
      extraCssText: `box-shadow: 0 4px 6px -1px rgba(0, 0, 0, ${dark ? '0.4' : '0.1'}); border-radius: 8px;`,
      formatter: function(params) {
        if (!params || !params.length) return ''
        
        const dateVal = params[0].value[0]
        const date = new Date(dateVal)
        const dateStr = date.getFullYear() + '-' +
                        String(date.getMonth() + 1).padStart(2, '0') + '-' +
                        String(date.getDate()).padStart(2, '0')
        
        let html = `<div style="font-weight: 600; margin-bottom: 6px; color: ${dark ? '#f3f4f6' : '#1f2937'}">${dateStr}</div>`
        params.forEach(param => {
          const val = param.value[1]
          const name = param.seriesName
          const color = param.color
          html += `
            <div style="display:flex; align-items:center; justify-content:space-between; gap:16px; margin-top:3px;">
              <div style="display:flex; align-items:center;">
                <span style="display:inline-block;margin-right:6px;border-radius:50%;width:8px;height:8px;background-color:${color};"></span>
                <span style="color: ${dark ? '#94a3b8' : '#4b5563'}">${name}</span>
              </div>
              <span style="font-weight:700; color: ${dark ? '#f3f4f6' : '#1f2937'}">${val.toLocaleString()} 下载</span>
            </div>`
        })
        return html
      }
    },
    grid: {
      left: '2%',
      right: '3%',
      bottom: window.innerWidth < 600 ? '18%' : '10%',
      top: '8%',
      containLabel: true
    },
    legend: {
      show: series.length > 0,
      bottom: window.innerWidth < 600 ? -2 : 0,
      type: 'scroll',
      icon: 'roundRect',
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: labelColor }
    },
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisLine: { lineStyle: { color: axisLineColor } },
      axisLabel: {
        color: labelColor,
        fontSize: 10,
        formatter: function(value) {
          const date = new Date(value)
          return String(date.getMonth() + 1).padStart(2, '0') + '/' + String(date.getDate()).padStart(2, '0')
        }
      },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      nameTextStyle: { color: labelColor },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: labelColor, fontSize: 10 },
      splitLine: { lineStyle: { type: 'dashed', color: splitLineColor } },
      min: 0
    },
    series: seriesList
  }

  chartInstance.setOption(option, true)
}

// 监听数据、过滤时间、主题状态变化以重绘
watch([isDark, () => props.pluginData, () => props.allPluginsData, () => props.dayData, localTimeRange], () => {
  if (chartInstance) {
    renderChart()
  }
}, { deep: true })

onMounted(() => {
  updateChartHeight()
  window.addEventListener('resize', updateChartHeight)
  
  // 延迟微调，确保容器容器高度在首屏计算完毕
  nextTick(() => {
    setTimeout(renderChart, 100)
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', updateChartHeight)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.trend-chart {
  width: 100%;
}

.chart-header {
  border-bottom: 1px solid rgb(var(--v-theme-outline-variant));
  padding-bottom: 12px;
}

.chart-container {
  width: 100%;
  overflow: hidden;
}

/* 移动端适配 */
@media (max-width: 600px) {
  .chart-header .d-flex {
    flex-direction: column;
    align-items: flex-start !important;
    gap: 12px;
  }

  .chart-header .d-flex:last-child {
    align-items: center !important;
    width: 100%;
    justify-content: space-between;
  }
}

.echart-wrapper {
  width: 100%;
  position: relative;
}

.trend-data-chip {
  height: 20px !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  padding: 0 8px !important;
}

.trend-time-toggle {
  height: 28px !important;
  border-radius: 6px !important;
}

.trend-toggle-btn {
  height: 28px !important;
  min-height: 28px !important;
  font-size: 11px !important;
  padding: 0 8px !important;
}
</style>
