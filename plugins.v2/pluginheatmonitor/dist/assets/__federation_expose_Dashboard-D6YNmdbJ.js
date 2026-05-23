import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-CRrXaTHX.js';
import { T as TrendChart } from './TrendChart-0RIadg9q.js';

const {renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,normalizeClass:_normalizeClass,normalizeStyle:_normalizeStyle,createElementVNode:_createElementVNode$1} = await importShared('vue');


const _hoisted_1$1 = { class: "heatmap-levels" };
const _hoisted_2$1 = { class: "heatmap-level mb-3" };
const _hoisted_3$1 = { class: "d-flex align-center flex-wrap" };
const _hoisted_4$1 = ["onClick"];
const _hoisted_5$1 = { class: "heatmap-level mb-3" };
const _hoisted_6$1 = { class: "d-flex align-center flex-wrap" };
const _hoisted_7$1 = ["onClick"];
const _hoisted_8$1 = { class: "heatmap-level" };
const _hoisted_9$1 = { class: "d-flex align-center flex-wrap" };

const {computed: computed$1} = await importShared('vue');



const _sfc_main$1 = {
  __name: 'HeatmapLevels',
  props: {
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
},
  emits: ['select-year', 'select-month'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

// 年份范围（最近5年，从左到右递增）
const yearRange = computed$1(() => {
  const currentYear = new Date().getFullYear();
  return Array.from({ length: 5 }, (_, i) => currentYear - 4 + i)
});

// 月份范围（最近12个月，从左到右递增）
const monthRange = computed$1(() => {
  const months = [];
  const currentDate = new Date();
  
  for (let i = 11; i >= 0; i--) {
    const date = new Date(currentDate.getFullYear(), currentDate.getMonth() - i, 1);
    const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    months.push(monthKey);
  }
  
  return months
});

// 天数范围（最近30天，从左到右递增）
const dayRange = computed$1(() => {
  const days = [];
  const currentDate = new Date();

  for (let i = 29; i >= 0; i--) {
    const date = new Date(currentDate.getTime() - i * 24 * 60 * 60 * 1000);
    // 使用本地时区的日期格式，与后端保持一致
    const dayKey = date.getFullYear() + '-' +
                   String(date.getMonth() + 1).padStart(2, '0') + '-' +
                   String(date.getDate()).padStart(2, '0');
    days.push(dayKey);
  }

  return days
});

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
  const downloads = props.yearData[year] || 0;
  const level = getYearLevel(downloads);
  const backgroundColor = getBlueColor(level);
  
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
  const downloads = props.monthData[month] || 0;
  const level = getMonthLevel(downloads);
  const backgroundColor = getOrangeColor(level);
  
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
  const today = new Date().toISOString().split('T')[0];

  // 如果是今天，优先使用实时增量数据
  if (day === today && props.liveIncrements[day] !== undefined) {
    return props.liveIncrements[day]
  }

  // 否则使用历史数据
  return props.dayData[day] || 0
}

// 获取天数单元格样式
function getDayCellStyle(day) {
  const downloads = getDayDisplayValue(day);
  const level = getDayLevel(downloads);
  const backgroundColor = getGreenColor(level);

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
  const [year, month] = monthKey.split('-');
  return `${year}年${month}月`
}

// 选择年份
function selectYear(year) {
  emit('select-year', year);
}

// 选择月份
function selectMonth(month) {
  emit('select-month', month);
}

return (_ctx, _cache) => {
  const _component_v_tooltip = _resolveComponent$1("v-tooltip");

  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createElementVNode$1("div", _hoisted_2$1, [
      _createElementVNode$1("div", _hoisted_3$1, [
        (_openBlock$1(true), _createElementBlock$1(_Fragment, null, _renderList(yearRange.value, (year) => {
          return (_openBlock$1(), _createElementBlock$1("div", {
            key: year,
            class: _normalizeClass(["heatmap-cell year-cell", { 'selected': __props.selectedYear === year }]),
            style: _normalizeStyle(getYearCellStyle(year)),
            onClick: $event => (selectYear(year))
          }, [
            _createVNode$1(_component_v_tooltip, {
              activator: "parent",
              location: "top"
            }, {
              default: _withCtx$1(() => [
                _createTextVNode$1(_toDisplayString$1(year) + "年: " + _toDisplayString$1((__props.yearData[year] || 0).toLocaleString()) + "增量 ", 1)
              ]),
              _: 2
            }, 1024)
          ], 14, _hoisted_4$1))
        }), 128))
      ])
    ]),
    _createElementVNode$1("div", _hoisted_5$1, [
      _createElementVNode$1("div", _hoisted_6$1, [
        (_openBlock$1(true), _createElementBlock$1(_Fragment, null, _renderList(monthRange.value, (month) => {
          return (_openBlock$1(), _createElementBlock$1("div", {
            key: month,
            class: _normalizeClass(["heatmap-cell month-cell", { 'selected': __props.selectedMonth === month }]),
            style: _normalizeStyle(getMonthCellStyle(month)),
            onClick: $event => (selectMonth(month))
          }, [
            _createVNode$1(_component_v_tooltip, {
              activator: "parent",
              location: "top"
            }, {
              default: _withCtx$1(() => [
                _createTextVNode$1(_toDisplayString$1(formatMonthTooltip(month)) + ": " + _toDisplayString$1((__props.monthData[month] || 0).toLocaleString()) + "增量 ", 1)
              ]),
              _: 2
            }, 1024)
          ], 14, _hoisted_7$1))
        }), 128))
      ])
    ]),
    _createElementVNode$1("div", _hoisted_8$1, [
      _cache[0] || (_cache[0] = _createElementVNode$1("div", { class: "text-caption text-medium-emphasis mb-1" }, "每日增量（近30天）", -1)),
      _createElementVNode$1("div", _hoisted_9$1, [
        (_openBlock$1(true), _createElementBlock$1(_Fragment, null, _renderList(dayRange.value, (day) => {
          return (_openBlock$1(), _createElementBlock$1("div", {
            key: day,
            class: "heatmap-cell day-cell",
            style: _normalizeStyle(getDayCellStyle(day))
          }, [
            _createVNode$1(_component_v_tooltip, {
              activator: "parent",
              location: "top"
            }, {
              default: _withCtx$1(() => [
                _createTextVNode$1(_toDisplayString$1(day) + ": " + _toDisplayString$1(getDayDisplayValue(day).toLocaleString()) + "增量 ", 1)
              ]),
              _: 2
            }, 1024)
          ], 4))
        }), 128))
      ])
    ])
  ]))
}
}

};
const HeatmapLevels = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-5e56b957"]]);

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "heat-monitor-dashboard" };
const _hoisted_2 = { class: "dashboard-content" };
const _hoisted_3 = {
  key: 0,
  class: "d-flex justify-center align-center py-8"
};
const _hoisted_4 = { class: "text-center" };
const _hoisted_5 = {
  key: 1,
  class: "dashboard-main"
};
const _hoisted_6 = { class: "status-header mb-4" };
const _hoisted_7 = { class: "d-flex align-center justify-space-between" };
const _hoisted_8 = { class: "d-flex align-center" };
const _hoisted_9 = { class: "text-subtitle-2 font-weight-medium" };
const _hoisted_10 = { class: "text-caption text-medium-emphasis" };
const _hoisted_11 = { class: "d-flex align-center" };
const _hoisted_12 = { class: "heatmap-section" };
const _hoisted_13 = {
  key: 0,
  class: "detail-section mt-4"
};
const _hoisted_14 = { class: "detail-content" };
const _hoisted_15 = { class: "d-flex justify-space-between align-center mb-2" };
const _hoisted_16 = { class: "d-flex justify-space-between align-center mb-2" };
const _hoisted_17 = { class: "d-flex justify-space-between align-center" };
const _hoisted_18 = { class: "text-caption text-medium-emphasis" };
const _hoisted_19 = { class: "d-flex align-center justify-space-between" };
const _hoisted_20 = { class: "d-flex align-center" };
const _hoisted_21 = { class: "d-flex align-center" };
const _hoisted_22 = {
  key: 0,
  class: "d-flex justify-center align-center py-8"
};
const _hoisted_23 = { class: "text-center" };
const _hoisted_24 = {
  key: 1,
  class: "dashboard-main"
};
const _hoisted_25 = { class: "status-overview mb-4" };
const _hoisted_26 = { class: "d-flex align-center justify-space-between" };
const _hoisted_27 = { class: "view-toggle-section mb-3" };
const _hoisted_28 = { class: "d-flex align-center justify-space-between" };
const _hoisted_29 = { class: "d-flex align-center" };
const _hoisted_30 = { class: "text-h6" };
const _hoisted_31 = {
  key: 0,
  class: "heatmap-section mb-4"
};
const _hoisted_32 = {
  key: 1,
  class: "trend-section mb-4"
};
const _hoisted_33 = {
  key: 2,
  class: "detail-section"
};
const _hoisted_34 = { class: "text-center" };
const _hoisted_35 = { class: "text-h6 font-weight-bold" };
const _hoisted_36 = { class: "text-center" };
const _hoisted_37 = { class: "text-h6 font-weight-bold" };
const _hoisted_38 = { class: "text-center" };
const _hoisted_39 = { class: "text-body-1 font-weight-bold" };
const _hoisted_40 = { class: "text-center" };
const _hoisted_41 = { class: "text-body-2 font-weight-bold" };
const {ref,reactive,computed,onMounted,onUnmounted} = await importShared('vue');

const {useDisplay} = await importShared('vuetify');

// 接收仪表板配置

const _sfc_main = {
  __name: 'Dashboard',
  props: {
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
},
  setup(__props) {

const props = __props;

// 使用Vuetify的响应式断点
const { xs, sm } = useDisplay();

// 从插件配置中获取Dashboard设置
const dashboardConfig = computed(() => {
  const pluginConfig = props.config?.attrs?.pluginConfig || {};
  return {
    refreshInterval: pluginConfig.dashboard_refresh_interval || 30,
    autoRefresh: pluginConfig.dashboard_auto_refresh !== false,
  }
});

// 组件状态
const initialLoading = ref(true);
const refreshing = ref(false);
const lastUpdateTime = ref('');
const viewMode = ref('heatmap'); // 'heatmap' 或 'trend'

// 热力图数据
const yearData = reactive({});
const monthData = reactive({});
const dayData = reactive({});
const liveIncrements = reactive({});

// 选择状态
const selectedYear = ref(null);
const selectedMonth = ref(null);
const selectedPeriod = ref(null);

// 统计数据
const totalDownloads = ref(0);

let refreshTimer = null;

// 计算属性
const statusText = computed(() => {
  const pluginCount = Object.keys(yearData).length;
  if (pluginCount === 0) return '暂无监控插件'
  return `监控 ${pluginCount} 个插件`
});

const selectedPeriodText = computed(() => {
  if (selectedYear.value && selectedMonth.value) {
    return `${selectedYear.value}年${selectedMonth.value.split('-')[1]}月`
  } else if (selectedYear.value) {
    return `${selectedYear.value}年`
  } else if (selectedMonth.value) {
    const [year, month] = selectedMonth.value.split('-');
    return `${year}年${month}月`
  }
  return ''
});

const selectedPeriodData = computed(() => {
  if (!selectedPeriod.value) return null

  // 根据选择的时间段返回相应数据
  if (selectedYear.value && selectedMonth.value) {
    // 月份数据
    const monthKey = selectedMonth.value;
    return {
      downloads: monthData[monthKey] || 0,
      growth: calculateGrowth(),
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
});

// 计算增长量
function calculateGrowth(type, key) {
  // 这里可以实现具体的增长量计算逻辑
  // 暂时返回模拟数据
  return Math.floor(Math.random() * 100)
}

// 处理年份选择
function handleSelectYear(year) {
  selectedYear.value = year;
  selectedMonth.value = null;
  selectedPeriod.value = 'year';

  // 可以在这里调用API获取指定年份的详细数据
  loadYearData(year);
}

// 处理月份选择
function handleSelectMonth(monthKey) {
  const [year, month] = monthKey.split('-');
  selectedYear.value = parseInt(year);
  selectedMonth.value = monthKey;
  selectedPeriod.value = 'month';

  // 可以在这里调用API获取指定月份的详细数据
  loadMonthData(monthKey);
}

// 加载年份数据
async function loadYearData(year) {
  try {
    const data = await props.api.get(`plugin/PluginHeatMonitor/year-data/${year}`);
    if (data) {
      // 更新年份相关的月份和日期数据
      Object.assign(monthData, data.monthData || {});
      Object.assign(dayData, data.dayData || {});
    }
  } catch (error) {
    console.error('加载年份数据失败:', error);
  }
}

// 加载月份数据
async function loadMonthData(monthKey) {
  try {
    const data = await props.api.get(`plugin/PluginHeatMonitor/month-data/${monthKey}`);
    if (data) {
      // 更新月份相关的日期数据
      Object.assign(dayData, data.dayData || {});
    }
  } catch (error) {
    console.error('加载月份数据失败:', error);
  }
}

// 获取仪表板数据
async function fetchDashboardData(isInitial = false) {
  if (!props.allowRefresh) return

  // 设置加载状态
  if (isInitial) {
    initialLoading.value = true;
  } else {
    refreshing.value = true;
  }

  try {
    // 获取热力图数据
    const heatmapData = await props.api.get('plugin/PluginHeatMonitor/heatmap-data');

    // 获取仪表板数据（包含真实的总下载量）
    const dashboardData = await props.api.get('plugin/PluginHeatMonitor/data');

    if (heatmapData) {
      // 更新热力图数据
      Object.assign(yearData, heatmapData.yearData || {});
      Object.assign(monthData, heatmapData.monthData || {});
      Object.assign(dayData, heatmapData.dayData || {});
    }

    if (dashboardData && dashboardData.status === 'success') {
      // 使用真实的总下载量（所有插件的当前下载量之和）
      totalDownloads.value = dashboardData.total_downloads || 0;

      // 计算今日的实际增长量总和（从daily_downloads获取）
      const today = new Date().toISOString().split('T')[0];
      const todayTotalGrowth = dashboardData.plugins?.reduce((sum, plugin) => {
        // 从每日下载数据中获取今日增长量
        const dailyDownloads = plugin.daily_downloads || {};
        const todayData = dailyDownloads[today];
        if (todayData && !todayData.is_historical) {
          return sum + (todayData.value || todayData || 0)
        }
        return sum
      }, 0) || 0;

      // 更新实时增量数据
      Object.assign(liveIncrements, { [today]: todayTotalGrowth });
    } else {
      // 如果无法获取仪表板数据，回退到热力图数据计算
      totalDownloads.value = Object.values(yearData).reduce((sum, val) => sum + val, 0);
    }

    // 更新最后更新时间
    lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });

  } catch (error) {
    console.error('获取仪表板数据失败:', error);
  } finally {
    // 清除加载状态
    initialLoading.value = false;
    refreshing.value = false;
  }
}

// 设置定时刷新
function setupRefreshTimer() {
  if (props.allowRefresh && dashboardConfig.value.autoRefresh) {
    const intervalMs = dashboardConfig.value.refreshInterval * 1000;

    refreshTimer = setInterval(() => {
      fetchDashboardData(false);
    }, intervalMs);
  }
}

// 初始化
onMounted(() => {
  setTimeout(() => {
    fetchDashboardData(true);
    setupRefreshTimer();
  }, 100);
});

// 清理
onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
  }
});

return (_ctx, _cache) => {
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_img = _resolveComponent("v-img");
  const _component_v_avatar = _resolveComponent("v-avatar");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_card_subtitle = _resolveComponent("v-card-subtitle");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (!__props.config?.attrs?.border)
      ? (_openBlock(), _createBlock(_component_v_card, {
          key: 0,
          flat: "",
          class: "dashboard-card"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_text, { class: "pa-0" }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_2, [
                  (initialLoading.value)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_3, [
                        _createElementVNode("div", _hoisted_4, [
                          _createVNode(_component_v_progress_circular, {
                            indeterminate: "",
                            color: "primary",
                            size: "40"
                          }),
                          _cache[1] || (_cache[1] = _createElementVNode("div", { class: "text-caption mt-2 text-medium-emphasis" }, "正在加载插件热度数据...", -1))
                        ])
                      ]))
                    : (_openBlock(), _createElementBlock("div", _hoisted_5, [
                        _createElementVNode("div", _hoisted_6, [
                          _createElementVNode("div", _hoisted_7, [
                            _createElementVNode("div", _hoisted_8, [
                              _createVNode(_component_v_avatar, {
                                size: "40",
                                class: "mr-3 plugin-logo"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_img, {
                                    src: "https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png",
                                    alt: "Heat Monitor Logo"
                                  }, {
                                    placeholder: _withCtx(() => [
                                      _createVNode(_component_v_icon, {
                                        color: "primary",
                                        size: "24"
                                      }, {
                                        default: _withCtx(() => _cache[2] || (_cache[2] = [
                                          _createTextVNode("mdi-chart-timeline-variant")
                                        ])),
                                        _: 1,
                                        __: [2]
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }),
                              _createElementVNode("div", null, [
                                _createElementVNode("div", _hoisted_9, [
                                  _cache[3] || (_cache[3] = _createTextVNode(" 插件热度监控 ")),
                                  (selectedPeriod.value)
                                    ? (_openBlock(), _createBlock(_component_v_chip, {
                                        key: 0,
                                        color: "primary",
                                        size: "x-small",
                                        variant: "tonal",
                                        class: "ml-2"
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(selectedPeriodText.value), 1)
                                        ]),
                                        _: 1
                                      }))
                                    : _createCommentVNode("", true)
                                ]),
                                _createElementVNode("div", _hoisted_10, _toDisplayString(statusText.value), 1)
                              ])
                            ]),
                            _createElementVNode("div", _hoisted_11, [
                              (refreshing.value)
                                ? (_openBlock(), _createBlock(_component_v_progress_circular, {
                                    key: 0,
                                    indeterminate: "",
                                    color: "primary",
                                    size: "16",
                                    width: "2",
                                    class: "mr-2"
                                  }))
                                : _createCommentVNode("", true),
                              _createVNode(_component_v_chip, {
                                color: "success",
                                size: "small",
                                variant: "tonal",
                                class: "text-caption"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(totalDownloads.value.toLocaleString()), 1)
                                ]),
                                _: 1
                              })
                            ])
                          ])
                        ]),
                        _createElementVNode("div", _hoisted_12, [
                          _createVNode(HeatmapLevels, {
                            "year-data": yearData,
                            "month-data": monthData,
                            "day-data": dayData,
                            "live-increments": liveIncrements,
                            "selected-year": selectedYear.value,
                            "selected-month": selectedMonth.value,
                            onSelectYear: handleSelectYear,
                            onSelectMonth: handleSelectMonth
                          }, null, 8, ["year-data", "month-data", "day-data", "live-increments", "selected-year", "selected-month"])
                        ]),
                        (selectedPeriodData.value)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_13, [
                              _createVNode(_component_v_card, {
                                variant: "outlined",
                                class: "detail-card"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_card_title, { class: "text-subtitle-2 pb-2" }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(selectedPeriodText.value) + "详细数据 ", 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_v_card_text, { class: "pt-0" }, {
                                    default: _withCtx(() => [
                                      _createElementVNode("div", _hoisted_14, [
                                        _createElementVNode("div", _hoisted_15, [
                                          _cache[4] || (_cache[4] = _createElementVNode("span", { class: "text-body-2" }, "总下载量", -1)),
                                          _createVNode(_component_v_chip, {
                                            size: "small",
                                            color: "primary",
                                            variant: "tonal"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(selectedPeriodData.value.downloads?.toLocaleString() || 0), 1)
                                            ]),
                                            _: 1
                                          })
                                        ]),
                                        _createElementVNode("div", _hoisted_16, [
                                          _cache[5] || (_cache[5] = _createElementVNode("span", { class: "text-body-2" }, "增长量", -1)),
                                          _createVNode(_component_v_chip, {
                                            size: "small",
                                            color: selectedPeriodData.value.growth > 0 ? 'success' : 'grey',
                                            variant: "tonal"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(" +" + _toDisplayString(selectedPeriodData.value.growth?.toLocaleString() || 0), 1)
                                            ]),
                                            _: 1
                                          }, 8, ["color"])
                                        ]),
                                        _createElementVNode("div", _hoisted_17, [
                                          _cache[6] || (_cache[6] = _createElementVNode("span", { class: "text-body-2" }, "最后更新", -1)),
                                          _createElementVNode("span", _hoisted_18, _toDisplayString(selectedPeriodData.value.lastUpdate || '未知'), 1)
                                        ])
                                      ])
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              })
                            ]))
                          : _createCommentVNode("", true)
                      ]))
                ])
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
      : (_openBlock(), _createBlock(_component_v_card, {
          key: 1,
          class: "dashboard-card"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_item, null, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_19, [
                  _createElementVNode("div", _hoisted_20, [
                    _createVNode(_component_v_avatar, {
                      size: "48",
                      class: "mr-4 plugin-logo"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_img, {
                          src: "https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png",
                          alt: "Heat Monitor Logo"
                        }, {
                          placeholder: _withCtx(() => [
                            _createVNode(_component_v_icon, {
                              color: "primary",
                              size: "28"
                            }, {
                              default: _withCtx(() => _cache[7] || (_cache[7] = [
                                _createTextVNode("mdi-chart-timeline-variant")
                              ])),
                              _: 1,
                              __: [7]
                            })
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    _createElementVNode("div", null, [
                      _createElementVNode("div", _hoisted_21, [
                        _createVNode(_component_v_card_title, { class: "text-h6 pa-0" }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(__props.config?.attrs?.title || '插件热度监控'), 1)
                          ]),
                          _: 1
                        }),
                        (selectedPeriod.value)
                          ? (_openBlock(), _createBlock(_component_v_chip, {
                              key: 0,
                              color: "primary",
                              size: "small",
                              variant: "tonal",
                              class: "ml-3"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(selectedPeriodText.value), 1)
                              ]),
                              _: 1
                            }))
                          : _createCommentVNode("", true)
                      ]),
                      (__props.config?.attrs?.subtitle)
                        ? (_openBlock(), _createBlock(_component_v_card_subtitle, {
                            key: 0,
                            class: "pa-0"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(__props.config.attrs.subtitle), 1)
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode("", true)
                    ])
                  ]),
                  (refreshing.value)
                    ? (_openBlock(), _createBlock(_component_v_progress_circular, {
                        key: 0,
                        indeterminate: "",
                        color: "primary",
                        size: "20",
                        width: "2"
                      }))
                    : _createCommentVNode("", true)
                ])
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                (initialLoading.value)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_22, [
                      _createElementVNode("div", _hoisted_23, [
                        _createVNode(_component_v_progress_circular, {
                          indeterminate: "",
                          color: "primary",
                          size: "40"
                        }),
                        _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-caption mt-2 text-medium-emphasis" }, "正在加载插件热度数据...", -1))
                      ])
                    ]))
                  : (_openBlock(), _createElementBlock("div", _hoisted_24, [
                      _createElementVNode("div", _hoisted_25, [
                        _createVNode(_component_v_alert, {
                          type: "success",
                          variant: "tonal",
                          density: "compact",
                          icon: "mdi-chart-timeline-variant"
                        }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_26, [
                              _createElementVNode("span", null, "监控 " + _toDisplayString(Object.keys(yearData).length) + " 个插件，总下载量 " + _toDisplayString(totalDownloads.value.toLocaleString()) + "（所有插件累计）", 1),
                              _createVNode(_component_v_chip, {
                                size: "small",
                                variant: "text"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(lastUpdateTime.value), 1)
                                ]),
                                _: 1
                              })
                            ])
                          ]),
                          _: 1
                        })
                      ]),
                      _createElementVNode("div", _hoisted_27, [
                        _createElementVNode("div", _hoisted_28, [
                          _createElementVNode("div", _hoisted_29, [
                            _createVNode(_component_v_icon, {
                              class: "mr-2",
                              color: "primary"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(viewMode.value === 'heatmap' ? 'mdi-chart-timeline-variant' : 'mdi-chart-line'), 1)
                              ]),
                              _: 1
                            }),
                            _createElementVNode("span", _hoisted_30, _toDisplayString(viewMode.value === 'heatmap' ? '下载量热力图' : '下载量趋势图'), 1)
                          ]),
                          _createVNode(_component_v_btn_toggle, {
                            modelValue: viewMode.value,
                            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((viewMode).value = $event)),
                            color: "primary",
                            size: "small",
                            variant: "outlined",
                            mandatory: ""
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_btn, {
                                value: "heatmap",
                                size: "small"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_icon, { start: "" }, {
                                    default: _withCtx(() => _cache[9] || (_cache[9] = [
                                      _createTextVNode("mdi-chart-timeline-variant")
                                    ])),
                                    _: 1,
                                    __: [9]
                                  }),
                                  _cache[10] || (_cache[10] = _createTextVNode(" 热力图 "))
                                ]),
                                _: 1,
                                __: [10]
                              }),
                              _createVNode(_component_v_btn, {
                                value: "trend",
                                size: "small"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_icon, { start: "" }, {
                                    default: _withCtx(() => _cache[11] || (_cache[11] = [
                                      _createTextVNode("mdi-chart-line")
                                    ])),
                                    _: 1,
                                    __: [11]
                                  }),
                                  _cache[12] || (_cache[12] = _createTextVNode(" 趋势图 "))
                                ]),
                                _: 1,
                                __: [12]
                              })
                            ]),
                            _: 1
                          }, 8, ["modelValue"])
                        ])
                      ]),
                      (viewMode.value === 'heatmap')
                        ? (_openBlock(), _createElementBlock("div", _hoisted_31, [
                            _createVNode(HeatmapLevels, {
                              "year-data": yearData,
                              "month-data": monthData,
                              "day-data": dayData,
                              "live-increments": liveIncrements,
                              "selected-year": selectedYear.value,
                              "selected-month": selectedMonth.value,
                              onSelectYear: handleSelectYear,
                              onSelectMonth: handleSelectMonth
                            }, null, 8, ["year-data", "month-data", "day-data", "live-increments", "selected-year", "selected-month"])
                          ]))
                        : (viewMode.value === 'trend')
                          ? (_openBlock(), _createElementBlock("div", _hoisted_32, [
                              _createVNode(TrendChart, {
                                api: __props.api,
                                "day-data": dayData
                              }, null, 8, ["api", "day-data"])
                            ]))
                          : _createCommentVNode("", true),
                      (selectedPeriodData.value)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_33, [
                            _createVNode(_component_v_card, {
                              variant: "tonal",
                              class: "detail-card"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_card_title, { class: "text-subtitle-2 pb-2" }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_v_icon, {
                                      class: "mr-2",
                                      size: "18"
                                    }, {
                                      default: _withCtx(() => _cache[13] || (_cache[13] = [
                                        _createTextVNode("mdi-information-outline")
                                      ])),
                                      _: 1,
                                      __: [13]
                                    }),
                                    _createTextVNode(" " + _toDisplayString(selectedPeriodText.value) + "详细数据 ", 1)
                                  ]),
                                  _: 1
                                }),
                                _createVNode(_component_v_card_text, { class: "pt-0" }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_v_row, { dense: "" }, {
                                      default: _withCtx(() => [
                                        _createVNode(_component_v_col, {
                                          cols: "6",
                                          sm: "3"
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_v_card, {
                                              variant: "tonal",
                                              class: "metric-card pa-3",
                                              color: "primary"
                                            }, {
                                              default: _withCtx(() => [
                                                _createElementVNode("div", _hoisted_34, [
                                                  _createVNode(_component_v_icon, {
                                                    size: "24",
                                                    class: "mb-2",
                                                    color: "primary"
                                                  }, {
                                                    default: _withCtx(() => _cache[14] || (_cache[14] = [
                                                      _createTextVNode("mdi-download")
                                                    ])),
                                                    _: 1,
                                                    __: [14]
                                                  }),
                                                  _createElementVNode("div", _hoisted_35, _toDisplayString(selectedPeriodData.value.downloads?.toLocaleString() || 0), 1),
                                                  _cache[15] || (_cache[15] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "总下载量", -1))
                                                ])
                                              ]),
                                              _: 1
                                            })
                                          ]),
                                          _: 1
                                        }),
                                        _createVNode(_component_v_col, {
                                          cols: "6",
                                          sm: "3"
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_v_card, {
                                              variant: "tonal",
                                              class: "metric-card pa-3",
                                              color: "success"
                                            }, {
                                              default: _withCtx(() => [
                                                _createElementVNode("div", _hoisted_36, [
                                                  _createVNode(_component_v_icon, {
                                                    size: "24",
                                                    class: "mb-2",
                                                    color: "success"
                                                  }, {
                                                    default: _withCtx(() => _cache[16] || (_cache[16] = [
                                                      _createTextVNode("mdi-trending-up")
                                                    ])),
                                                    _: 1,
                                                    __: [16]
                                                  }),
                                                  _createElementVNode("div", _hoisted_37, " +" + _toDisplayString(selectedPeriodData.value.growth?.toLocaleString() || 0), 1),
                                                  _cache[17] || (_cache[17] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "增长量", -1))
                                                ])
                                              ]),
                                              _: 1
                                            })
                                          ]),
                                          _: 1
                                        }),
                                        _createVNode(_component_v_col, {
                                          cols: "6",
                                          sm: "3"
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_v_card, {
                                              variant: "tonal",
                                              class: "metric-card pa-3",
                                              color: "info"
                                            }, {
                                              default: _withCtx(() => [
                                                _createElementVNode("div", _hoisted_38, [
                                                  _createVNode(_component_v_icon, {
                                                    size: "24",
                                                    class: "mb-2",
                                                    color: "info"
                                                  }, {
                                                    default: _withCtx(() => _cache[18] || (_cache[18] = [
                                                      _createTextVNode("mdi-calendar")
                                                    ])),
                                                    _: 1,
                                                    __: [18]
                                                  }),
                                                  _createElementVNode("div", _hoisted_39, _toDisplayString(selectedPeriodData.value.period || '未知'), 1),
                                                  _cache[19] || (_cache[19] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "时间段", -1))
                                                ])
                                              ]),
                                              _: 1
                                            })
                                          ]),
                                          _: 1
                                        }),
                                        _createVNode(_component_v_col, {
                                          cols: "6",
                                          sm: "3"
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_v_card, {
                                              variant: "tonal",
                                              class: "metric-card pa-3",
                                              color: "warning"
                                            }, {
                                              default: _withCtx(() => [
                                                _createElementVNode("div", _hoisted_40, [
                                                  _createVNode(_component_v_icon, {
                                                    size: "24",
                                                    class: "mb-2",
                                                    color: "warning"
                                                  }, {
                                                    default: _withCtx(() => _cache[20] || (_cache[20] = [
                                                      _createTextVNode("mdi-clock-outline")
                                                    ])),
                                                    _: 1,
                                                    __: [20]
                                                  }),
                                                  _createElementVNode("div", _hoisted_41, _toDisplayString(selectedPeriodData.value.lastUpdate || '未知'), 1),
                                                  _cache[21] || (_cache[21] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "最后更新", -1))
                                                ])
                                              ]),
                                              _: 1
                                            })
                                          ]),
                                          _: 1
                                        })
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]))
                        : _createCommentVNode("", true)
                    ]))
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
  ]))
}
}

};
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e72b01fe"]]);

export { Dashboard as default };
