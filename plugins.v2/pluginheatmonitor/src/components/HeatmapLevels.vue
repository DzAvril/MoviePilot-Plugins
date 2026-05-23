<template>
  <div class="heatmap-levels">
    <!-- 年份级别热力图 -->
    <div class="heatmap-level mb-3">
      <div class="d-flex align-center flex-wrap">
        <div
          v-for="year in yearRange"
          :key="year"
          class="heatmap-cell year-cell"
          :class="{ 'selected': selectedYear === year }"
          :style="getYearCellStyle(year)"
          @click="selectYear(year)"
        >
          <v-tooltip activator="parent" location="top">
            {{ year }}年: {{ (yearData[year] || 0).toLocaleString() }}增量
          </v-tooltip>
        </div>
      </div>
    </div>

    <!-- 月份级别热力图 -->
    <div class="heatmap-level mb-3">
      <div class="d-flex align-center flex-wrap">
        <div
          v-for="month in monthRange"
          :key="month"
          class="heatmap-cell month-cell"
          :class="{ 'selected': selectedMonth === month }"
          :style="getMonthCellStyle(month)"
          @click="selectMonth(month)"
        >
          <v-tooltip activator="parent" location="top">
            {{ formatMonthTooltip(month) }}: {{ (monthData[month] || 0).toLocaleString() }}增量
          </v-tooltip>
        </div>
      </div>
    </div>

    <!-- 天数级别热力图 -->
    <div class="heatmap-level">
      <div class="text-caption text-medium-emphasis mb-1">每日增量（近30天）</div>
      <div class="d-flex align-center flex-wrap">
        <div
          v-for="day in dayRange"
          :key="day"
          class="heatmap-cell day-cell"
          :style="getDayCellStyle(day)"
        >
          <v-tooltip activator="parent" location="top">
            {{ day }}: {{ getDayDisplayValue(day).toLocaleString() }}增量
          </v-tooltip>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  yearData: {
    type: Object,
    default: () => ({})
  },
  monthData: {
    type: Object,
    default: () => ({})
  },
  dayData: {
    type: Object,
    default: () => ({})
  },
  selectedYear: {
    type: Number,
    default: null
  },
  selectedMonth: {
    type: String,
    default: null
  },
  // 新增：实时增量数据（用于显示今日的实时增量）
  liveIncrements: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['select-year', 'select-month'])

// 年份范围（最近5年，从左到右递增）
const yearRange = computed(() => {
  const currentYear = new Date().getFullYear()
  return Array.from({ length: 5 }, (_, i) => currentYear - 4 + i)
})

// 月份范围（最近12个月，从左到右递增）
const monthRange = computed(() => {
  const months = []
  const currentDate = new Date()
  
  for (let i = 11; i >= 0; i--) {
    const date = new Date(currentDate.getFullYear(), currentDate.getMonth() - i, 1)
    const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
    months.push(monthKey)
  }
  
  return months
})

// 天数范围（最近30天，从左到右递增）
const dayRange = computed(() => {
  const days = []
  const currentDate = new Date()

  for (let i = 29; i >= 0; i--) {
    const date = new Date(currentDate.getTime() - i * 24 * 60 * 60 * 1000)
    // 使用本地时区的日期格式，与后端保持一致
    const dayKey = date.getFullYear() + '-' +
                   String(date.getMonth() + 1).padStart(2, '0') + '-' +
                   String(date.getDate()).padStart(2, '0')
    days.push(dayKey)
  }

  return days
})

// 获取年份等级
function getYearLevel(downloads) {
  if (downloads >= 50000) return 4
  if (downloads >= 20000) return 3
  if (downloads >= 5000) return 2
  if (downloads > 0) return 1
  return 0
}

// 获取月份等级
function getMonthLevel(downloads) {
  if (downloads >= 5000) return 4
  if (downloads >= 2000) return 3
  if (downloads >= 500) return 2
  if (downloads > 0) return 1
  return 0
}

// 获取天数等级
function getDayLevel(downloads) {
  if (downloads >= 1000) return 4
  if (downloads >= 500) return 3
  if (downloads >= 100) return 2
  if (downloads > 0) return 1
  return 0
}

// 获取蓝色系颜色（年份）
function getBlueColor(level) {
  return `var(--heat-year-${level})`
}

// 获取橙色系颜色（月份）
function getOrangeColor(level) {
  return `var(--heat-month-${level})`
}

// 获取绿色系颜色（天数）
function getGreenColor(level) {
  return `var(--heat-day-${level})`
}

// 获取年份单元格样式
function getYearCellStyle(year) {
  const downloads = props.yearData[year] || 0
  const level = getYearLevel(downloads)
  const backgroundColor = getBlueColor(level)
  
  return {
    backgroundColor,
    width: '16px',
    height: '16px',
    borderRadius: '2px',
    margin: '2px',
    cursor: 'pointer',
    transition: 'all 0.2s ease'
  }
}

// 获取月份单元格样式
function getMonthCellStyle(month) {
  const downloads = props.monthData[month] || 0
  const level = getMonthLevel(downloads)
  const backgroundColor = getOrangeColor(level)
  
  return {
    backgroundColor,
    width: '14px',
    height: '14px',
    borderRadius: '2px',
    margin: '1px',
    cursor: 'pointer',
    transition: 'all 0.2s ease'
  }
}

// 获取天数显示值（优先使用实时增量，回退到历史数据）
function getDayDisplayValue(day) {
  const today = new Date().toISOString().split('T')[0]

  // 如果是今天，优先使用实时增量数据
  if (day === today && props.liveIncrements[day] !== undefined) {
    return props.liveIncrements[day]
  }

  // 否则使用历史数据
  return props.dayData[day] || 0
}

// 获取天数单元格样式
function getDayCellStyle(day) {
  const downloads = getDayDisplayValue(day)
  const level = getDayLevel(downloads)
  const backgroundColor = getGreenColor(level)

  return {
    backgroundColor,
    width: '12px',
    height: '12px',
    borderRadius: '2px',
    margin: '1px',
    transition: 'all 0.2s ease'
  }
}

// 格式化月份提示文本
function formatMonthTooltip(monthKey) {
  const [year, month] = monthKey.split('-')
  return `${year}年${month}月`
}

// 选择年份
function selectYear(year) {
  emit('select-year', year)
}

// 选择月份
function selectMonth(month) {
  emit('select-month', month)
}
</script>

<style scoped>
.heatmap-levels {
  user-select: none;
}

.heatmap-level {
  margin-bottom: 8px;
}

.heatmap-cell {
  display: inline-block;
  transition: all 0.2s ease;
}

.heatmap-cell:hover {
  transform: scale(1.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  z-index: 10;
  position: relative;
}

.heatmap-cell.selected {
  transform: scale(1.3);
  z-index: 20;
  position: relative;
}

.year-cell.selected {
  box-shadow: 0 0 0 2px var(--heat-year-4);
}

.month-cell.selected {
  box-shadow: 0 0 0 2px var(--heat-month-4);
}

/* 响应式设计 */
@media (max-width: 600px) {
  .heatmap-cell {
    margin: 1px;
  }
  
  .year-cell {
    width: 14px !important;
    height: 14px !important;
  }
  
  .month-cell {
    width: 12px !important;
    height: 12px !important;
  }
  
  .day-cell {
    width: 10px !important;
    height: 10px !important;
  }
}
</style>
