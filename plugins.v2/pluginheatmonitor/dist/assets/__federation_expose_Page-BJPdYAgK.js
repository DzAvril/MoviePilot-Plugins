import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-CRrXaTHX.js';
import { T as TrendChart } from './TrendChart-0RIadg9q.js';

const {createElementVNode:_createElementVNode$6,openBlock:_openBlock$6,createElementBlock:_createElementBlock$5,createCommentVNode:_createCommentVNode$5,createTextVNode:_createTextVNode$6,resolveComponent:_resolveComponent$5,withCtx:_withCtx$5,createVNode:_createVNode$5,toDisplayString:_toDisplayString$6,normalizeStyle:_normalizeStyle$3,normalizeClass:_normalizeClass$4,createBlock:_createBlock$5} = await importShared('vue');

const {computed: computed$4} = await importShared('vue');

const {toDisplayString:_toDisplayString$5,createElementVNode:_createElementVNode$5,createTextVNode:_createTextVNode$5,openBlock:_openBlock$5,createElementBlock:_createElementBlock$4,createCommentVNode:_createCommentVNode$4,normalizeClass:_normalizeClass$3,normalizeStyle:_normalizeStyle$2} = await importShared('vue');


const _hoisted_1$5 = { class: "heat-progress-container w-100" };
const _hoisted_2$5 = { class: "d-flex align-center justify-space-between mb-1 text-caption text-medium-emphasis font-weight-medium" };
const _hoisted_3$5 = { class: "text-truncate" };
const _hoisted_4$5 = { class: "font-weight-bold ml-2" };
const _hoisted_5$5 = { class: "ml-1 text-primary" };
const _hoisted_6$4 = { class: "progress-bar-track position-relative" };
const _hoisted_7$4 = {
  key: 0,
  class: "shine-effect"
};

const {computed: computed$3} = await importShared('vue');



const _sfc_main$5 = {
  __name: 'ProgressBar',
  props: {
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
},
  setup(__props) {

const props = __props;

const progressPercent = computed$3(() => {
  if (!props.target || props.target <= 0) return 0
  const pct = (props.current / props.target) * 100;
  return Math.min(Math.round(pct), 1000) // 允许超过100%，但在轨道上限制为100%
});

const clampedPercent = computed$3(() => {
  return Math.min(progressPercent.value, 100)
});

const isCompleted = computed$3(() => {
  return progressPercent.value >= 100
});

const fillClass = computed$3(() => {
  const pct = progressPercent.value;
  if (pct >= 100) return 'progress-fill--completed'
  if (pct >= 80) return 'progress-fill--success'
  if (pct >= 30) return 'progress-fill--primary'
  return 'progress-fill--default'
});

return (_ctx, _cache) => {
  return (_openBlock$5(), _createElementBlock$4("div", _hoisted_1$5, [
    _createElementVNode$5("div", _hoisted_2$5, [
      _createElementVNode$5("span", _hoisted_3$5, _toDisplayString$5(__props.label), 1),
      _createElementVNode$5("span", _hoisted_4$5, [
        _createTextVNode$5(_toDisplayString$5(__props.current.toLocaleString()) + " / " + _toDisplayString$5(__props.target.toLocaleString()) + _toDisplayString$5(__props.unit) + " ", 1),
        _createElementVNode$5("span", _hoisted_5$5, "(" + _toDisplayString$5(progressPercent.value) + "%)", 1)
      ])
    ]),
    _createElementVNode$5("div", _hoisted_6$4, [
      _createElementVNode$5("div", {
        class: _normalizeClass$3(["progress-bar-fill", fillClass.value]),
        style: _normalizeStyle$2({ width: `${clampedPercent.value}%` })
      }, [
        (isCompleted.value)
          ? (_openBlock$5(), _createElementBlock$4("div", _hoisted_7$4))
          : _createCommentVNode$4("", true)
      ], 6)
    ])
  ]))
}
}

};
const ProgressBar = /*#__PURE__*/_export_sfc(_sfc_main$5, [['__scopeId',"data-v-57492fce"]]);

const {createTextVNode:_createTextVNode$4,resolveComponent:_resolveComponent$4,withCtx:_withCtx$4,createVNode:_createVNode$4,createElementVNode:_createElementVNode$4,openBlock:_openBlock$4,createBlock:_createBlock$4,createCommentVNode:_createCommentVNode$3,createElementBlock:_createElementBlock$3,toDisplayString:_toDisplayString$4,normalizeClass:_normalizeClass$2} = await importShared('vue');


const _hoisted_1$4 = { class: "avatar-placeholder" };
const _hoisted_2$4 = {
  key: 1,
  class: "avatar-placeholder"
};
const _hoisted_3$4 = { class: "plugin-list-item__content" };
const _hoisted_4$4 = { class: "plugin-list-item__header" };
const _hoisted_5$4 = { class: "plugin-list-item__name text-truncate" };
const _hoisted_6$3 = {
  key: 0,
  class: "plugin-list-item__desc text-truncate"
};
const _hoisted_7$3 = { class: "mt-1" };


const _sfc_main$4 = {
  __name: 'PluginListItem',
  props: {
  plugin: {
    type: Object,
    required: true
  },
  isActive: {
    type: Boolean,
    default: false
  }
},
  emits: ['click'],
  setup(__props) {



return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$4("v-icon");
  const _component_v_img = _resolveComponent$4("v-img");
  const _component_v_avatar = _resolveComponent$4("v-avatar");
  const _component_v_chip = _resolveComponent$4("v-chip");

  return (_openBlock$4(), _createElementBlock$3("div", {
    class: _normalizeClass$2(["plugin-list-item cursor-pointer transition-all", { 'plugin-list-item--active': __props.isActive }]),
    onClick: _cache[0] || (_cache[0] = $event => (_ctx.$emit('click')))
  }, [
    _createVNode$4(_component_v_avatar, {
      size: "36",
      class: "plugin-avatar"
    }, {
      default: _withCtx$4(() => [
        (__props.plugin.plugin_icon || __props.plugin.icon)
          ? (_openBlock$4(), _createBlock$4(_component_v_img, {
              key: 0,
              src: __props.plugin.plugin_icon || __props.plugin.icon
            }, {
              placeholder: _withCtx$4(() => [
                _createElementVNode$4("div", _hoisted_1$4, [
                  _createVNode$4(_component_v_icon, {
                    color: "primary",
                    size: "20"
                  }, {
                    default: _withCtx$4(() => _cache[1] || (_cache[1] = [
                      _createTextVNode$4("mdi-puzzle-outline")
                    ])),
                    _: 1,
                    __: [1]
                  })
                ])
              ]),
              _: 1
            }, 8, ["src"]))
          : (_openBlock$4(), _createElementBlock$3("div", _hoisted_2$4, [
              _createVNode$4(_component_v_icon, {
                color: "primary",
                size: "20"
              }, {
                default: _withCtx$4(() => _cache[2] || (_cache[2] = [
                  _createTextVNode$4("mdi-puzzle-outline")
                ])),
                _: 1,
                __: [2]
              })
            ]))
      ]),
      _: 1
    }),
    _createElementVNode$4("div", _hoisted_3$4, [
      _createElementVNode$4("div", _hoisted_4$4, [
        _createElementVNode$4("span", _hoisted_5$4, _toDisplayString$4(__props.plugin.plugin_name || __props.plugin.name), 1),
        _createVNode$4(_component_v_chip, {
          size: "x-small",
          color: "primary",
          variant: "flat",
          class: "plugin-list-item__downloads"
        }, {
          default: _withCtx$4(() => [
            _createTextVNode$4(_toDisplayString$4((__props.plugin.current_downloads || __props.plugin.downloads || 0).toLocaleString()), 1)
          ]),
          _: 1
        })
      ]),
      (__props.plugin.desc)
        ? (_openBlock$4(), _createElementBlock$3("div", _hoisted_6$3, _toDisplayString$4(__props.plugin.desc), 1))
        : _createCommentVNode$3("", true),
      _createElementVNode$4("div", _hoisted_7$3, [
        _createVNode$4(ProgressBar, {
          current: __props.plugin.increment_since_last || 0,
          target: __props.plugin.download_increment || 100,
          unit: ""
        }, null, 8, ["current", "target"])
      ])
    ])
  ], 2))
}
}

};
const PluginListItem = /*#__PURE__*/_export_sfc(_sfc_main$4, [['__scopeId',"data-v-6054ae39"]]);

const {resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,toDisplayString:_toDisplayString$3,createElementVNode:_createElementVNode$3,createTextVNode:_createTextVNode$3,withCtx:_withCtx$3,openBlock:_openBlock$3,createBlock:_createBlock$3} = await importShared('vue');


const _hoisted_1$3 = { class: "status-footer__content py-3 px-4 d-flex align-center justify-space-between text-caption text-medium-emphasis" };
const _hoisted_2$3 = { class: "d-flex align-center" };
const _hoisted_3$3 = { class: "font-weight-bold text-high-emphasis" };
const _hoisted_4$3 = { class: "d-flex align-center gap-4" };
const _hoisted_5$3 = { class: "d-none d-sm-inline-flex align-center" };


const _sfc_main$3 = {
  __name: 'StatusFooter',
  props: {
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
  },
  running: {
    type: Boolean,
    default: false
  }
},
  emits: ['run-once'],
  setup(__props, { emit: __emit }) {

const emit = __emit;



return (_ctx, _cache) => {
  const _component_v_badge = _resolveComponent$3("v-badge");
  const _component_v_icon = _resolveComponent$3("v-icon");
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_card = _resolveComponent$3("v-card");

  return (_openBlock$3(), _createBlock$3(_component_v_card, {
    class: "status-footer heat-glass-card",
    variant: "flat"
  }, {
    default: _withCtx$3(() => [
      _createElementVNode$3("div", _hoisted_1$3, [
        _createElementVNode$3("div", _hoisted_2$3, [
          _createVNode$3(_component_v_badge, {
            dot: "",
            color: __props.refreshing ? 'primary' : 'success',
            inline: "",
            class: "mr-2 mb-0.5"
          }, null, 8, ["color"]),
          _createElementVNode$3("span", null, [
            _cache[1] || (_cache[1] = _createTextVNode$3(" 最后检查时间: ")),
            _createElementVNode$3("span", _hoisted_3$3, _toDisplayString$3(__props.lastUpdateTime || '未知'), 1)
          ])
        ]),
        _createElementVNode$3("div", _hoisted_4$3, [
          _createVNode$3(_component_v_btn, {
            variant: "text",
            density: "comfortable",
            size: "small",
            color: "primary",
            class: "run-once-btn px-2 text-caption font-weight-bold",
            loading: __props.running,
            onClick: _cache[0] || (_cache[0] = $event => (emit('run-once')))
          }, {
            default: _withCtx$3(() => [
              _createVNode$3(_component_v_icon, {
                size: "14",
                class: "mr-1"
              }, {
                default: _withCtx$3(() => _cache[2] || (_cache[2] = [
                  _createTextVNode$3("mdi-play-circle-outline")
                ])),
                _: 1,
                __: [2]
              }),
              _cache[3] || (_cache[3] = _createTextVNode$3(" 立即运行一次 "))
            ]),
            _: 1,
            __: [3]
          }, 8, ["loading"]),
          _createElementVNode$3("span", _hoisted_5$3, [
            _createVNode$3(_component_v_icon, {
              size: "14",
              class: "mr-1"
            }, {
              default: _withCtx$3(() => _cache[4] || (_cache[4] = [
                _createTextVNode$3("mdi-puzzle-outline")
              ])),
              _: 1,
              __: [4]
            }),
            _createElementVNode$3("span", null, "pluginheatmonitor v" + _toDisplayString$3(__props.version), 1),
            _cache[5] || (_cache[5] = _createElementVNode$3("span", { class: "mx-1.5" }, "•", -1)),
            _createElementVNode$3("span", null, "By " + _toDisplayString$3(__props.author), 1)
          ])
        ])
      ])
    ]),
    _: 1
  }))
}
}

};
const StatusFooter = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-1cbd4639"]]);

const {renderList:_renderList$2,Fragment:_Fragment$2,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,toDisplayString:_toDisplayString$2,createElementVNode:_createElementVNode$2,normalizeStyle:_normalizeStyle$1,normalizeClass:_normalizeClass$1,Teleport:_Teleport$1} = await importShared('vue');


const _hoisted_1$2 = { class: "github-heatmap" };
const _hoisted_2$2 = {
  key: 0,
  class: "heatmaps-container"
};
const _hoisted_3$2 = {
  key: 0,
  class: "plugin-header mb-3"
};
const _hoisted_4$2 = { class: "d-flex align-center justify-space-between" };
const _hoisted_5$2 = { class: "d-flex align-center" };
const _hoisted_6$2 = { class: "text-h6 font-weight-bold" };
const _hoisted_7$2 = { class: "text-caption text-medium-emphasis" };
const _hoisted_8$2 = { class: "github-heatmap-wrapper" };
const _hoisted_9$2 = { class: "heatmap-inner-container" };
const _hoisted_10$2 = { class: "month-labels" };
const _hoisted_11$2 = { class: "heatmap-main" };
const _hoisted_12$2 = { class: "heatmap-grid" };
const _hoisted_13$2 = ["onMouseenter", "onClick"];
const _hoisted_14$2 = { class: "heatmap-legend" };
const _hoisted_15$2 = { class: "legend-content" };
const _hoisted_16$2 = { class: "legend-scale" };
const _hoisted_17$2 = { class: "legend-squares" };
const _hoisted_18$2 = {
  key: 1,
  class: "stats-container mt-4"
};
const _hoisted_19$2 = { class: "stat-item" };
const _hoisted_20$2 = { class: "text-h6 font-weight-bold" };
const _hoisted_21$2 = { class: "stat-item" };
const _hoisted_22$2 = { class: "text-h6 font-weight-bold" };
const _hoisted_23$2 = { class: "stat-item" };
const _hoisted_24$2 = { class: "text-h6 font-weight-bold" };
const _hoisted_25$2 = { class: "stat-item" };
const _hoisted_26$1 = { class: "text-h6 font-weight-bold" };
const _hoisted_27$1 = { class: "stat-item" };
const _hoisted_28$1 = { class: "text-h6 font-weight-bold" };
const _hoisted_29$1 = {
  key: 1,
  class: "text-center py-8"
};
const _hoisted_30$1 = { class: "text-body-2" };

const {ref: ref$2,reactive: reactive$2,computed: computed$2,watch: watch$2,onMounted: onMounted$2,onUnmounted: onUnmounted$1} = await importShared('vue');

const {useTheme} = await importShared('vuetify');



const _sfc_main$2 = {
  __name: 'GitHubHeatmap',
  props: {
  api: {
    type: Object,
    required: true
  },
  selectedPluginId: {
    type: String,
    default: ''
  },
  selectedYear: {
    type: Number,
    default: () => new Date().getFullYear()
  },
  hideStats: {
    type: Boolean,
    default: false
  },
  hideHeader: {
    type: Boolean,
    default: false
  }
},
  emits: ['square-clicked', 'update:selectedYear', 'years-loaded'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const theme = useTheme();
const isDark = computed$2(() => {
  return document.documentElement.getAttribute('data-theme') === 'dark' || theme.global.name.value === 'dark'
});

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

function isOutlierData(dayData) {
  if (typeof dayData === 'object' && dayData !== null) {
    return dayData.is_outlier || false
  }
  return false
}

// 状态
const loading = ref$2(false);
const currentPluginHeatmapData = ref$2(null);
const selectedYear = computed$2({
  get() {
    return props.selectedYear
  },
  set(val) {
    emit('update:selectedYear', val);
  }
});
const pluginHeatmaps = computed$2(() => {
  return currentPluginHeatmapData.value ? [currentPluginHeatmapData.value] : []
});
const pluginOptions = ref$2([]);

// Tooltip状态
const tooltip = reactive$2({
  show: false,
  content: '',
  style: {}
});



// 重置相关状态
const resetting = ref$2({}); // 记录每个插件的重置状态
const resetDialog = reactive$2({
  show: false,
  loading: false,
  pluginId: '',
  pluginName: '',
  currentDownloads: 0
});

// 提示消息状态
const snackbar = reactive$2({
  show: false,
  message: '',
  color: 'success'
});

// 计算可用年份
const availableYears = computed$2(() => {
  const years = new Set();
  pluginHeatmaps.value.forEach(plugin => {
    if (plugin.yearData) {
      Object.keys(plugin.yearData).forEach(year => {
        years.add(parseInt(year));
      });
    }
  });
  const yearArray = Array.from(years).sort((a, b) => b - a);
  return yearArray.length > 0 ? yearArray : [new Date().getFullYear()]
});

// 监听可用年份的变化并通知父组件
watch$2(availableYears, (newYears) => {
  emit('years-loaded', newYears);
}, { immediate: true, deep: true });

// 生成指定插件的热力图数据
function getHeatmapSquares(pluginData) {
  if (!pluginData?.dayData) return []

  const squares = [];
  const startDate = new Date(selectedYear.value, 0, 1);
  new Date(selectedYear.value, 11, 31);

  // 找到年初的第一个周日（GitHub从周日开始）
  const firstSunday = new Date(startDate);
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() - 1);
  }

  const current = new Date(firstSunday);
  const dayData = pluginData.dayData;

  // 智能过滤异常值：排除历史数据和异常值，只使用正常增量数据计算最大值
  const normalValues = Object.values(dayData)
    .filter(item => {
      const value = getDayValue(item);
      const isHistorical = isHistoricalData(item);
      const isOutlier = isOutlierData(item);
      return value > 0 && !isHistorical && !isOutlier
    })
    .map(item => getDayValue(item));

  // 如果没有正常数据，则使用所有非历史数据
  const fallbackValues = Object.values(dayData)
    .filter(item => {
      const value = getDayValue(item);
      const isHistorical = isHistoricalData(item);
      return value > 0 && !isHistorical
    })
    .map(item => getDayValue(item));

  const maxValue = Math.max(...(normalValues.length > 0 ? normalValues : fallbackValues), 1);

  // 生成53周 × 7天的网格
  for (let week = 0; week < 53; week++) {
    for (let day = 0; day < 7; day++) {
      // 使用本地时区的日期格式，与后端保持一致
      const dateStr = current.getFullYear() + '-' +
                      String(current.getMonth() + 1).padStart(2, '0') + '-' +
                      String(current.getDate()).padStart(2, '0');

      const dayDataItem = dayData[dateStr];
      const value = getDayValue(dayDataItem);
      const isHistorical = isHistoricalData(dayDataItem);
      const isOutlier = isOutlierData(dayDataItem);

      // 计算颜色等级：异常值和历史数据使用特殊处理
      let level = 0;
      if (value > 0) {
        if (isHistorical || isOutlier) {
          // 历史数据和异常值使用较低的等级，避免影响整体颜色深度
          level = Math.min(2, Math.ceil((value / maxValue) * 2));
        } else {
          // 正常数据使用完整的等级范围
          level = Math.min(4, Math.ceil((value / maxValue) * 4));
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
        isHistorical,
        isOutlier
      });

      current.setDate(current.getDate() + 1);
    }
  }

  return squares
}

// 生成月份标签 - 响应式计算
const monthLabels = computed$2(() => {
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const labels = [];
  const seenMonths = new Set();
  
  const startDate = new Date(selectedYear.value, 0, 1);
  const firstSunday = new Date(startDate);
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() - 1);
  }
  
  for (let w = 0; w < 53; w++) {
    const currentSunday = new Date(firstSunday);
    currentSunday.setDate(firstSunday.getDate() + w * 7);
    
    let monthIdx = currentSunday.getMonth();
    if (currentSunday.getFullYear() < selectedYear.value) {
      monthIdx = 0;
    }
    
    if (!seenMonths.has(monthIdx) && (currentSunday.getFullYear() === selectedYear.value || w === 0)) {
      seenMonths.add(monthIdx);
      labels.push({
        name: monthNames[monthIdx],
        weekIndex: w
      });
    }
  }
  return labels
});

// 获取插件图标
function getPluginIcon(pluginId) {
  const plugin = pluginOptions.value.find(p => (p.plugin_id === pluginId || p.id === pluginId));
  return plugin?.plugin_icon || plugin?.icon || null
}

// 统计方法
function getTotalDownloads(pluginData) {
  // 返回插件的真实总下载量，而不是每日增量的累和
  return pluginData?.current_downloads || 0
}

function getActiveDays(pluginData) {
  if (!pluginData?.dayData) return 0
  return Object.entries(pluginData.dayData)
    .filter(([date, dayDataItem]) => {
      const year = new Date(date).getFullYear();
      const value = getDayValue(dayDataItem);
      const isHistorical = isHistoricalData(dayDataItem);
      const isOutlier = isOutlierData(dayDataItem);
      return year === selectedYear.value && value > 0 && !isHistorical && !isOutlier
    })
    .length
}

function getMaxDayContribution(pluginData) {
  if (!pluginData?.dayData) return 0
  return Math.max(...Object.entries(pluginData.dayData)
    .filter(([date, dayDataItem]) => {
      const year = new Date(date).getFullYear();
      const isHistorical = isHistoricalData(dayDataItem);
      const isOutlier = isOutlierData(dayDataItem);
      return year === selectedYear.value && !isHistorical && !isOutlier
    })
    .map(([, dayDataItem]) => getDayValue(dayDataItem)), 0)
}

function getCurrentStreak(pluginData) {
  if (!pluginData?.dayData) return 0

  // 正确的连续天数计算：从今天开始往前推，检查连续性
  const today = new Date();
  let streak = 0;
  let currentDate = new Date(today);

  // 从今天开始往前检查每一天
  while (currentDate.getFullYear() === selectedYear.value) {
    const dateStr = currentDate.getFullYear() + '-' +
                   String(currentDate.getMonth() + 1).padStart(2, '0') + '-' +
                   String(currentDate.getDate()).padStart(2, '0');

    const dayDataItem = pluginData.dayData[dateStr];

    // 检查这一天是否有数据且不是历史数据或异常值
    if (dayDataItem && !isHistoricalData(dayDataItem) && !isOutlierData(dayDataItem)) {
      const value = getDayValue(dayDataItem);
      if (value > 0) {
        streak++;
      } else {
        // 遇到没有数据的天，停止计数
        break
      }
    } else {
      // 遇到没有数据的天，停止计数
      break
    }

    // 往前推一天
    currentDate.setDate(currentDate.getDate() - 1);
  }

  return streak
}

function getTodayContribution(pluginData) {
  if (!pluginData?.dayData) return 0
  // 使用本地时区的日期，与后端保持一致
  const today = new Date().getFullYear() + '-' +
                String(new Date().getMonth() + 1).padStart(2, '0') + '-' +
                String(new Date().getDate()).padStart(2, '0');
  const todayData = pluginData.dayData[today];
  // 只返回非历史数据且非异常值的值
  if (todayData && !isHistoricalData(todayData) && !isOutlierData(todayData)) {
    return getDayValue(todayData)
  }
  return 0
}

// 热力图颜色表（和 tokens.css 一致，不依赖 CSS 变量继承）
const HEAT_COLORS_LIGHT = ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39'];
const HEAT_COLORS_DARK  = ['#2d333b', '#1a4731', '#1d6340', '#2ea043', '#3fb950'];

// 方法
function getSquareClass(level, isHistorical = false, isOutlier = false) {
  const baseClass = `github-level-${level}`;
  if (isHistorical) {
    return `${baseClass} historical-data`
  } else if (isOutlier) {
    return `${baseClass} outlier-data`
  }
  return baseClass
}

function getSquareStyle(square) {
  const colors = isDark.value ? HEAT_COLORS_DARK : HEAT_COLORS_LIGHT;
  const level = Math.min(square.level ?? 0, 4);
  return {
    gridColumn: square.week + 1,
    gridRow: square.day + 1,
    backgroundColor: colors[level]
  }
}

function showTooltip(event, square) {
  const date = square.date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });

  // 根据数据类型显示不同的tooltip文本，并格式化数值
  const formattedValue = square.value.toLocaleString();
  if (square.isHistorical) {
    tooltip.content = `${formattedValue} 历史下载量 on ${date}`;
  } else if (square.isOutlier) {
    tooltip.content = `${formattedValue} 异常值 (已排除) on ${date}`;
  } else {
    tooltip.content = `${formattedValue} downloads on ${date}`;
  }

  // 使用clientX/clientY获取相对于视窗的鼠标位置
  // 因为我们使用position: fixed，所以不需要考虑页面滚动
  const mouseX = event.clientX;
  const mouseY = event.clientY;

  // 获取视窗信息
  const viewportWidth = window.innerWidth;

  // 计算tooltip的偏移量
  const tooltipOffset = 12;

  // 预估tooltip宽度（基于内容长度）
  const estimatedWidth = Math.max(120, tooltip.content.length * 8);
  const estimatedHeight = 32;

  // 默认位置：鼠标上方居中
  let left = mouseX;
  let top = mouseY - tooltipOffset - estimatedHeight;
  let transform = 'translateX(-50%)';

  // 如果tooltip会超出右边界，调整为右对齐
  if (left + estimatedWidth / 2 > viewportWidth - 10) {
    left = mouseX - 10;
    transform = 'translateX(-100%)';
  }
  // 如果tooltip会超出左边界，调整为左对齐
  else if (left - estimatedWidth / 2 < 10) {
    left = mouseX + 10;
    transform = 'translateX(0)';
  }

  // 如果tooltip会超出上边界，显示在鼠标下方
  if (top < 10) {
    top = mouseY + tooltipOffset;
  }

  // 深色/浅色模式内联样式
  const dark = isDark.value;
  const tooltipBaseStyle = dark
    ? {
        background: 'rgba(30, 41, 59, 0.97)',
        color: '#f3f4f6',
        border: '1px solid #334155',
        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.4)'
      }
    : {
        background: 'rgba(255, 255, 255, 0.97)',
        color: '#1f2937',
        border: '1px solid #e5e7eb',
        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)'
      };

  tooltip.style = {
    ...tooltipBaseStyle,
    position: 'fixed',
    left: left + 'px',
    top: top + 'px',
    transform: transform,
    zIndex: 1000
  };
  tooltip.show = true;
}

function hideTooltip() {
  tooltip.show = false;
}

function onSquareClick(square, pluginData) {
  emit('square-clicked', { square, plugin: pluginData });
}

async function loadHeatmapData(pluginId) {
  if (!pluginId) {
    currentPluginHeatmapData.value = null;
    return
  }
  loading.value = true;
  try {
    // 获取插件列表以匹配 icon 和 name
    if (pluginOptions.value.length === 0) {
      const listData = await props.api.get('plugin/PluginHeatMonitor/plugin-list');
      if (listData && listData.status === 'success') {
        pluginOptions.value = listData.plugins || [];
      }
    }

    const result = await props.api.get(`plugin/PluginHeatMonitor/plugin-heatmap?plugin_id=${pluginId}`);
    if (result && result.status === 'success') {
      currentPluginHeatmapData.value = result;
    } else {
      currentPluginHeatmapData.value = null;
    }
  } catch (error) {
    console.error(`加载插件 ${pluginId} 热力图数据失败:`, error);
    currentPluginHeatmapData.value = null;
  } finally {
    loading.value = false;
  }
}

async function loadAllPluginHeatmaps() {
  await loadHeatmapData(props.selectedPluginId);
}

// 监听选中的插件变化
watch$2(() => props.selectedPluginId, async (newId) => {
  await loadHeatmapData(newId);
});

// 显示重置确认对话框
function showResetDialog(pluginData) {
  resetDialog.pluginId = pluginData.plugin_id || pluginData.id;
  resetDialog.pluginName = pluginData.plugin_name || pluginData.name;
  resetDialog.currentDownloads = pluginData.current_downloads || 0;
  resetDialog.show = true;
}

// 确认重置
async function confirmReset() {
  resetDialog.loading = true;
  resetting.value[resetDialog.pluginId] = true;

  try {
    const response = await props.api.post('plugin/PluginHeatMonitor/reset-plugin-heatmap', {
      plugin_id: resetDialog.pluginId
    });

    if (response && response.status === 'success') {
      // 重置成功，显示成功消息
      snackbar.message = `插件「${resetDialog.pluginName}」的热力图数据已成功重置`;
      snackbar.color = 'success';
      snackbar.show = true;

      // 重新加载热力图数据
      await loadAllPluginHeatmaps();
    } else {
      // 重置失败
      snackbar.message = response?.message || '重置失败，请稍后重试';
      snackbar.color = 'error';
      snackbar.show = true;
    }
  } catch (error) {
    console.error('重置热力图数据失败:', error);
    snackbar.message = '重置失败，请检查网络连接后重试';
    snackbar.color = 'error';
    snackbar.show = true;
  } finally {
    resetDialog.loading = false;
    resetDialog.show = false;
    resetting.value[resetDialog.pluginId] = false;
  }
}

// 监听年份变化
watch$2(selectedYear, () => {
  // 年份变化时不需要重新加载数据，只需要重新渲染
});

// 窗口大小变化时重新计算
// 初始化
onMounted$2(() => {
  if (props.selectedPluginId) {
    loadHeatmapData(props.selectedPluginId);
  }
});

// 清理
onUnmounted$1(() => {
});





return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_img = _resolveComponent$2("v-img");
  const _component_v_avatar = _resolveComponent$2("v-avatar");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_card_title = _resolveComponent$2("v-card-title");
  const _component_v_alert = _resolveComponent$2("v-alert");
  const _component_v_card_text = _resolveComponent$2("v-card-text");
  const _component_v_spacer = _resolveComponent$2("v-spacer");
  const _component_v_card_actions = _resolveComponent$2("v-card-actions");
  const _component_v_card = _resolveComponent$2("v-card");
  const _component_v_dialog = _resolveComponent$2("v-dialog");
  const _component_v_snackbar = _resolveComponent$2("v-snackbar");

  return (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
    (pluginHeatmaps.value.length > 0)
      ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_2$2, [
          (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(pluginHeatmaps.value, (pluginData) => {
            return (_openBlock$2(), _createElementBlock$2("div", {
              key: pluginData.plugin_id,
              class: "plugin-heatmap-section mb-6"
            }, [
              (!__props.hideHeader)
                ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_3$2, [
                    _createElementVNode$2("div", _hoisted_4$2, [
                      _createElementVNode$2("div", _hoisted_5$2, [
                        _createVNode$2(_component_v_avatar, {
                          size: "32",
                          class: "mr-3"
                        }, {
                          default: _withCtx$2(() => [
                            (getPluginIcon(pluginData.plugin_id || pluginData.id))
                              ? (_openBlock$2(), _createBlock$2(_component_v_img, {
                                  key: 0,
                                  src: getPluginIcon(pluginData.plugin_id || pluginData.id)
                                }, {
                                  placeholder: _withCtx$2(() => [
                                    _createVNode$2(_component_v_icon, null, {
                                      default: _withCtx$2(() => _cache[4] || (_cache[4] = [
                                        _createTextVNode$2("mdi-puzzle")
                                      ])),
                                      _: 1,
                                      __: [4]
                                    })
                                  ]),
                                  _: 2
                                }, 1032, ["src"]))
                              : (_openBlock$2(), _createBlock$2(_component_v_icon, { key: 1 }, {
                                  default: _withCtx$2(() => _cache[5] || (_cache[5] = [
                                    _createTextVNode$2("mdi-puzzle")
                                  ])),
                                  _: 1,
                                  __: [5]
                                }))
                          ]),
                          _: 2
                        }, 1024),
                        _createElementVNode$2("div", null, [
                          _createElementVNode$2("h3", _hoisted_6$2, _toDisplayString$2(pluginData.plugin_name || pluginData.name), 1),
                          _createElementVNode$2("div", _hoisted_7$2, _toDisplayString$2(getTotalDownloads(pluginData).toLocaleString()) + " downloads in " + _toDisplayString$2(selectedYear.value), 1)
                        ])
                      ]),
                      _createVNode$2(_component_v_btn, {
                        size: "small",
                        color: "warning",
                        variant: "outlined",
                        "prepend-icon": "mdi-refresh",
                        onClick: $event => (showResetDialog(pluginData)),
                        loading: resetting.value[pluginData.plugin_id || pluginData.id],
                        disabled: resetting.value[pluginData.plugin_id || pluginData.id]
                      }, {
                        default: _withCtx$2(() => _cache[6] || (_cache[6] = [
                          _createTextVNode$2(" 重置数据 ")
                        ])),
                        _: 2,
                        __: [6]
                      }, 1032, ["onClick", "loading", "disabled"])
                    ])
                  ]))
                : _createCommentVNode$2("", true),
              _createElementVNode$2("div", _hoisted_8$2, [
                _createElementVNode$2("div", _hoisted_9$2, [
                  _createElementVNode$2("div", _hoisted_10$2, [
                    (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(monthLabels.value, (month, index) => {
                      return (_openBlock$2(), _createElementBlock$2("span", {
                        key: index,
                        class: "month-label",
                        style: _normalizeStyle$1({ left: `calc(${month.weekIndex} * (var(--square-size) + var(--square-gap)))` })
                      }, _toDisplayString$2(month.name), 5))
                    }), 128))
                  ]),
                  _createElementVNode$2("div", _hoisted_11$2, [
                    _cache[7] || (_cache[7] = _createElementVNode$2("div", { class: "weekday-labels" }, [
                      _createElementVNode$2("span", {
                        class: "weekday-label",
                        style: {"grid-row":"2"}
                      }, "Mon"),
                      _createElementVNode$2("span", {
                        class: "weekday-label",
                        style: {"grid-row":"4"}
                      }, "Wed"),
                      _createElementVNode$2("span", {
                        class: "weekday-label",
                        style: {"grid-row":"6"}
                      }, "Fri")
                    ], -1)),
                    _createElementVNode$2("div", _hoisted_12$2, [
                      (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(getHeatmapSquares(pluginData), (square, index) => {
                        return (_openBlock$2(), _createElementBlock$2("div", {
                          key: index,
                          class: _normalizeClass$1(["heatmap-square", getSquareClass(square.level, square.isHistorical, square.isOutlier)]),
                          style: _normalizeStyle$1(getSquareStyle(square)),
                          onMouseenter: $event => (showTooltip($event, square)),
                          onMouseleave: hideTooltip,
                          onClick: $event => (onSquareClick(square, pluginData))
                        }, null, 46, _hoisted_13$2))
                      }), 128))
                    ])
                  ])
                ])
              ]),
              _createElementVNode$2("div", _hoisted_14$2, [
                _createElementVNode$2("div", _hoisted_15$2, [
                  _createElementVNode$2("div", _hoisted_16$2, [
                    _cache[8] || (_cache[8] = _createElementVNode$2("span", { class: "legend-label" }, "Less", -1)),
                    _createElementVNode$2("div", _hoisted_17$2, [
                      (_openBlock$2(), _createElementBlock$2(_Fragment$2, null, _renderList$2(5, (level) => {
                        return _createElementVNode$2("div", {
                          key: level,
                          class: _normalizeClass$1(["legend-square", getSquareClass(level - 1)]),
                          style: _normalizeStyle$1({ backgroundColor: (isDark.value ? HEAT_COLORS_DARK : HEAT_COLORS_LIGHT)[level - 1] })
                        }, null, 6)
                      }), 64))
                    ]),
                    _cache[9] || (_cache[9] = _createElementVNode$2("span", { class: "legend-label" }, "More", -1))
                  ])
                ])
              ]),
              (!__props.hideStats)
                ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_18$2, [
                    _createElementVNode$2("div", _hoisted_19$2, [
                      _createElementVNode$2("div", _hoisted_20$2, _toDisplayString$2(getTotalDownloads(pluginData).toLocaleString()), 1),
                      _cache[10] || (_cache[10] = _createElementVNode$2("div", { class: "text-caption" }, "总下载量", -1))
                    ]),
                    _createElementVNode$2("div", _hoisted_21$2, [
                      _createElementVNode$2("div", _hoisted_22$2, _toDisplayString$2(getActiveDays(pluginData).toLocaleString()), 1),
                      _cache[11] || (_cache[11] = _createElementVNode$2("div", { class: "text-caption" }, "活跃天数", -1))
                    ]),
                    _createElementVNode$2("div", _hoisted_23$2, [
                      _createElementVNode$2("div", _hoisted_24$2, _toDisplayString$2(getMaxDayContribution(pluginData).toLocaleString()), 1),
                      _cache[12] || (_cache[12] = _createElementVNode$2("div", { class: "text-caption" }, "最高单日", -1))
                    ]),
                    _createElementVNode$2("div", _hoisted_25$2, [
                      _createElementVNode$2("div", _hoisted_26$1, _toDisplayString$2(getTodayContribution(pluginData).toLocaleString()), 1),
                      _cache[13] || (_cache[13] = _createElementVNode$2("div", { class: "text-caption" }, "今日新增", -1))
                    ]),
                    _createElementVNode$2("div", _hoisted_27$1, [
                      _createElementVNode$2("div", _hoisted_28$1, _toDisplayString$2(getCurrentStreak(pluginData).toLocaleString()), 1),
                      _cache[14] || (_cache[14] = _createElementVNode$2("div", { class: "text-caption" }, "连续天数", -1))
                    ])
                  ]))
                : _createCommentVNode$2("", true)
            ]))
          }), 128))
        ]))
      : (_openBlock$2(), _createElementBlock$2("div", _hoisted_29$1, [
          _createVNode$2(_component_v_icon, {
            size: "64",
            color: "grey-lighten-2"
          }, {
            default: _withCtx$2(() => _cache[15] || (_cache[15] = [
              _createTextVNode$2("mdi-chart-timeline-variant")
            ])),
            _: 1,
            __: [15]
          }),
          _cache[16] || (_cache[16] = _createElementVNode$2("div", { class: "text-h6 mt-2 text-medium-emphasis" }, "暂无监控插件数据", -1)),
          _cache[17] || (_cache[17] = _createElementVNode$2("div", { class: "text-caption text-medium-emphasis" }, "请先配置要监控的插件", -1))
        ])),
    (_openBlock$2(), _createBlock$2(_Teleport$1, { to: "body" }, [
      (tooltip.show)
        ? (_openBlock$2(), _createElementBlock$2("div", {
            key: 0,
            class: "heatmap-tooltip",
            style: _normalizeStyle$1(tooltip.style)
          }, _toDisplayString$2(tooltip.content), 5))
        : _createCommentVNode$2("", true)
    ])),
    _createVNode$2(_component_v_dialog, {
      modelValue: resetDialog.show,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((resetDialog.show) = $event)),
      "max-width": "500"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_card, null, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card_title, { class: "text-h5 d-flex align-center" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  color: "warning",
                  class: "mr-2"
                }, {
                  default: _withCtx$2(() => _cache[18] || (_cache[18] = [
                    _createTextVNode$2("mdi-alert-circle")
                  ])),
                  _: 1,
                  __: [18]
                }),
                _cache[19] || (_cache[19] = _createTextVNode$2(" 确认重置热力图数据 "))
              ]),
              _: 1,
              __: [19]
            }),
            _createVNode$2(_component_v_card_text, null, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_alert, {
                  type: "warning",
                  variant: "tonal",
                  class: "mb-4"
                }, {
                  default: _withCtx$2(() => [
                    _cache[20] || (_cache[20] = _createElementVNode$2("div", { class: "text-subtitle-2 mb-2" }, "⚠️ 重要提醒", -1)),
                    _createElementVNode$2("div", null, "此操作将清空插件「" + _toDisplayString$2(resetDialog.pluginName) + "」的所有每日下载数据，包括：", 1),
                    _cache[21] || (_cache[21] = _createElementVNode$2("ul", { class: "mt-2" }, [
                      _createElementVNode$2("li", null, "所有历史热力图数据"),
                      _createElementVNode$2("li", null, "活跃天数统计"),
                      _createElementVNode$2("li", null, "最高单日下载记录"),
                      _createElementVNode$2("li", null, "连续活跃天数记录")
                    ], -1))
                  ]),
                  _: 1,
                  __: [20,21]
                }),
                _createElementVNode$2("div", _hoisted_30$1, [
                  _createTextVNode$2(" 重置后将以当前总下载量（" + _toDisplayString$2(resetDialog.currentDownloads?.toLocaleString()) + "）作为新的基准， ", 1),
                  _cache[22] || (_cache[22] = _createElementVNode$2("strong", null, "立即开始重新记录增量数据", -1)),
                  _cache[23] || (_cache[23] = _createTextVNode$2("。 "))
                ]),
                _cache[24] || (_cache[24] = _createElementVNode$2("div", { class: "text-body-2 mt-2 text-error" }, [
                  _createElementVNode$2("strong", null, "此操作不可撤销，请谨慎操作！")
                ], -1))
              ]),
              _: 1,
              __: [24]
            }),
            _createVNode$2(_component_v_card_actions, { class: "pa-4" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_spacer),
                _createVNode$2(_component_v_btn, {
                  variant: "outlined",
                  onClick: _cache[0] || (_cache[0] = $event => (resetDialog.show = false)),
                  disabled: resetDialog.loading
                }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, { start: "" }, {
                      default: _withCtx$2(() => _cache[25] || (_cache[25] = [
                        _createTextVNode$2("mdi-close")
                      ])),
                      _: 1,
                      __: [25]
                    }),
                    _cache[26] || (_cache[26] = _createTextVNode$2(" 取消 "))
                  ]),
                  _: 1,
                  __: [26]
                }, 8, ["disabled"]),
                _createVNode$2(_component_v_btn, {
                  color: "warning",
                  variant: "elevated",
                  onClick: confirmReset,
                  loading: resetDialog.loading,
                  "prepend-icon": "mdi-refresh"
                }, {
                  default: _withCtx$2(() => _cache[27] || (_cache[27] = [
                    _createTextVNode$2(" 确认重置数据 ")
                  ])),
                  _: 1,
                  __: [27]
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$2(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: 4000,
      location: "top"
    }, {
      actions: _withCtx$2(() => [
        _createVNode$2(_component_v_btn, {
          variant: "text",
          onClick: _cache[2] || (_cache[2] = $event => (snackbar.show = false))
        }, {
          default: _withCtx$2(() => _cache[28] || (_cache[28] = [
            _createTextVNode$2(" 关闭 ")
          ])),
          _: 1,
          __: [28]
        })
      ]),
      default: _withCtx$2(() => [
        _createTextVNode$2(_toDisplayString$2(snackbar.message) + " ", 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const GitHubHeatmap = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-f7f3202c"]]);

const {toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,mergeProps:_mergeProps$1,renderList:_renderList$1,Fragment:_Fragment$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1,normalizeClass:_normalizeClass,normalizeStyle:_normalizeStyle,Teleport:_Teleport} = await importShared('vue');


const _hoisted_1$1 = { class: "d-flex align-center justify-space-between width-100" };
const _hoisted_2$1 = { class: "d-flex align-center gap-2" };
const _hoisted_3$1 = { class: "text-subtitle-1 font-weight-bold text-high-emphasis" };
const _hoisted_4$1 = {
  key: 1,
  class: "d-flex align-center gap-1"
};
const _hoisted_5$1 = {
  key: 0,
  class: "d-flex justify-center align-center py-12"
};
const _hoisted_6$1 = {
  key: 1,
  class: "detail-container"
};
const _hoisted_7$1 = { class: "d-flex align-center justify-space-between py-1 mb-2" };
const _hoisted_8$1 = { class: "d-flex align-center" };
const _hoisted_9$1 = { class: "d-flex flex-column" };
const _hoisted_10$1 = { class: "d-flex align-center gap-1" };
const _hoisted_11$1 = {
  class: "text-subtitle-1 font-weight-bold text-high-emphasis",
  style: {"line-height":"1.25"}
};
const _hoisted_12$1 = {
  class: "text-caption text-medium-emphasis",
  style: {"opacity":"0.6"}
};
const _hoisted_13$1 = { class: "text-caption text-medium-emphasis mt-1" };
const _hoisted_14$1 = { class: "stats-grid" };
const _hoisted_15$1 = { class: "stats-card pa-2 text-center" };
const _hoisted_16$1 = { class: "stats-value text-success" };
const _hoisted_17$1 = { class: "stats-card pa-2 text-center" };
const _hoisted_18$1 = { class: "stats-value text-primary" };
const _hoisted_19$1 = { class: "stats-card pa-2 text-center" };
const _hoisted_20$1 = { class: "stats-value text-warning" };
const _hoisted_21$1 = { class: "stats-card pa-2 text-center" };
const _hoisted_22$1 = { class: "stats-value text-info" };
const _hoisted_23$1 = { class: "vis-section" };
const _hoisted_24$1 = {
  key: 0,
  class: "heatmap-view-container position-relative"
};
const _hoisted_25$1 = {
  key: 1,
  class: "trend-view-container"
};

const {ref: ref$1,reactive: reactive$1,computed: computed$1,watch: watch$1,onMounted: onMounted$1,onUnmounted} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'PluginDetail',
  props: {
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
},
  emits: ['data-changed'],
  setup(__props, { expose: __expose, emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref$1(true);
const resetting = ref$1(false);
const showResetConfirm = ref$1(false);
const viewMode = ref$1('heatmap');
const timeRange = ref$1('30');
const selectedYear = ref$1(new Date().getFullYear());
const availableYears = ref$1([new Date().getFullYear()]);
const pluginDetailData = ref$1(null);
const windowWidth = ref$1(window.innerWidth);

// Tooltip state
const tooltip = reactive$1({
  show: false,
  content: '',
  style: {}
});

function handleResize() {
  windowWidth.value = window.innerWidth;
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
  loading.value = true;
  try {
    const response = await props.api.get(`plugin/PluginHeatMonitor/plugin-heatmap?plugin_id=${props.plugin.plugin_id || props.plugin.id}`);
    if (response && response.status === 'success') {
      pluginDetailData.value = {
        plugin_id: props.plugin.plugin_id || props.plugin.id,
        plugin_name: props.plugin.plugin_name || props.plugin.name,
        plugin_icon: props.plugin.plugin_icon || props.plugin.icon,
        daily_downloads: response.dayData || response.daily_downloads || {},
        current_downloads: response.current_downloads || props.plugin.downloads || 0
      };

      // Extract available years from daily downloads keys
      const years = new Set();
      Object.keys(pluginDetailData.value.daily_downloads).forEach(dateStr => {
        const yr = new Date(dateStr).getFullYear();
        if (!isNaN(yr)) years.add(yr);
      });
      if (years.size > 0) {
        availableYears.value = Array.from(years).sort((a, b) => b - a);
      } else {
        availableYears.value = [new Date().getFullYear()];
      }
      
      if (!availableYears.value.includes(selectedYear.value)) {
        selectedYear.value = availableYears.value[0];
      }
    }
  } catch (error) {
    console.error('加载插件详情数据失败:', error);
  } finally {
    loading.value = false;
  }
}

// Reset data
async function resetPluginData() {
  resetting.value = true;
  try {
    const pId = props.plugin.plugin_id || props.plugin.id;
    const response = await props.api.post('plugin/PluginHeatMonitor/reset-plugin-heatmap', {
      plugin_id: pId
    });
    if (response && response.status === 'success') {
      showResetConfirm.value = false;
      await loadDetailData();
      emit('data-changed');
    }
  } catch (error) {
    console.error('重置数据失败:', error);
  } finally {
    resetting.value = false;
  }
}

// Compute statistics
const activeDays = computed$1(() => {
  if (!pluginDetailData.value?.daily_downloads) return 0
  return Object.entries(pluginDetailData.value.daily_downloads)
    .filter(([date, val]) => {
      const yr = new Date(date).getFullYear();
      const dVal = getDayValue(val);
      return yr === selectedYear.value && dVal > 0 && !isHistoricalData(val) && !isOutlierData(val)
    }).length
});

const maxDayIncrement = computed$1(() => {
  if (!pluginDetailData.value?.daily_downloads) return 0
  const values = Object.entries(pluginDetailData.value.daily_downloads)
    .filter(([date, val]) => {
      const yr = new Date(date).getFullYear();
      return yr === selectedYear.value && !isHistoricalData(val) && !isOutlierData(val)
    })
    .map(([, val]) => getDayValue(val));
  return values.length > 0 ? Math.max(...values) : 0
});

const currentStreak = computed$1(() => {
  if (!pluginDetailData.value?.daily_downloads) return 0
  const today = new Date();
  let streak = 0;
  let curr = new Date(today);
  
  while (curr.getFullYear() === selectedYear.value) {
    const dStr = curr.getFullYear() + '-' +
                 String(curr.getMonth() + 1).padStart(2, '0') + '-' +
                 String(curr.getDate()).padStart(2, '0');
    const item = pluginDetailData.value.daily_downloads[dStr];
    if (item && getDayValue(item) > 0 && !isHistoricalData(item) && !isOutlierData(item)) {
      streak++;
    } else {
      break
    }
    curr.setDate(curr.getDate() - 1);
  }
  return streak
});

// Generate heatmap squares for selected year
computed$1(() => {
  if (!pluginDetailData.value?.daily_downloads) return []
  
  const squares = [];
  const startDate = new Date(selectedYear.value, 0, 1);
  const firstSunday = new Date(startDate);
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() - 1);
  }
  
  const current = new Date(firstSunday);
  const dailyDownloads = pluginDetailData.value.daily_downloads;
  
  // Find max value for scaling color level
  const normalValues = Object.values(dailyDownloads)
    .filter(val => getDayValue(val) > 0 && !isHistoricalData(val) && !isOutlierData(val))
    .map(val => getDayValue(val));
  const maxValue = Math.max(...(normalValues.length > 0 ? normalValues : [1]), 1);
  
  for (let week = 0; week < 53; week++) {
    for (let day = 0; day < 7; day++) {
      const dateStr = current.getFullYear() + '-' +
                      String(current.getMonth() + 1).padStart(2, '0') + '-' +
                      String(current.getDate()).padStart(2, '0');
      
      const dayData = dailyDownloads[dateStr];
      const value = getDayValue(dayData);
      const isHist = isHistoricalData(dayData);
      const isOut = isOutlierData(dayData);
      
      let level = 0;
      if (value > 0) {
        if (isHist || isOut) {
          level = Math.min(2, Math.ceil((value / maxValue) * 2));
        } else {
          level = Math.min(4, Math.ceil((value / maxValue) * 4));
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
      });
      
      current.setDate(current.getDate() + 1);
    }
  }
  return squares
});

// Month labels positions
computed$1(() => {
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  let sqSize = 13;
  let gap = 2;
  
  if (windowWidth.value <= 768) {
    sqSize = 10;
  }
  
  const columnWidth = sqSize + gap;
  const labels = [];
  const seenMonths = new Set();
  
  const startDate = new Date(selectedYear.value, 0, 1);
  const firstSunday = new Date(startDate);
  while (firstSunday.getDay() !== 0) {
    firstSunday.setDate(firstSunday.getDate() - 1);
  }
  
  for (let w = 0; w < 53; w++) {
    const currentSunday = new Date(firstSunday);
    currentSunday.setDate(firstSunday.getDate() + w * 7);
    
    let monthIdx = currentSunday.getMonth();
    if (currentSunday.getFullYear() < selectedYear.value) {
      monthIdx = 0;
    }
    
    if (!seenMonths.has(monthIdx) && (currentSunday.getFullYear() === selectedYear.value || w === 0)) {
      seenMonths.add(monthIdx);
      labels.push({
        name: monthNames[monthIdx],
        position: w * columnWidth
      });
    }
  }
  return labels
});

// Watchers
watch$1(() => props.plugin, () => {
  loadDetailData();
}, { deep: true });

onMounted$1(() => {
  loadDetailData();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
});

__expose({
  loadDetailData
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_chip = _resolveComponent$1("v-chip");
  const _component_v_list_item_title = _resolveComponent$1("v-list-item-title");
  const _component_v_list_item = _resolveComponent$1("v-list-item");
  const _component_v_list = _resolveComponent$1("v-list");
  const _component_v_menu = _resolveComponent$1("v-menu");
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_btn_group = _resolveComponent$1("v-btn-group");
  const _component_v_progress_circular = _resolveComponent$1("v-progress-circular");
  const _component_v_img = _resolveComponent$1("v-img");
  const _component_v_avatar = _resolveComponent$1("v-avatar");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card_title = _resolveComponent$1("v-card-title");
  const _component_v_spacer = _resolveComponent$1("v-spacer");
  const _component_v_card_actions = _resolveComponent$1("v-card-actions");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createBlock$1(_component_v_card, {
    class: _normalizeClass(["plugin-detail-card overflow-hidden", [__props.flat ? 'elevation-0 bg-transparent border-0 pa-0' : 'heat-glass-card']]),
    style: _normalizeStyle(__props.flat ? 'background: transparent !important;' : ''),
    variant: "flat"
  }, {
    default: _withCtx$1(() => [
      _createElementVNode$1("div", {
        class: _normalizeClass([__props.flat ? 'py-1 px-0' : 'pa-2 pa-sm-4 pb-2'])
      }, [
        _createElementVNode$1("div", _hoisted_1$1, [
          _createElementVNode$1("div", _hoisted_2$1, [
            _createVNode$1(_component_v_icon, {
              color: "primary",
              size: "24"
            }, {
              default: _withCtx$1(() => [
                _createTextVNode$1(_toDisplayString$1(viewMode.value === 'heatmap' ? 'mdi-calendar-month-outline' : 'mdi-chart-line'), 1)
              ]),
              _: 1
            }),
            _createElementVNode$1("span", _hoisted_3$1, _toDisplayString$1(viewMode.value === 'heatmap' ? '全局热度日历' : '下载增量趋势'), 1),
            (viewMode.value === 'heatmap')
              ? (_openBlock$1(), _createBlock$1(_component_v_menu, {
                  key: 0,
                  location: "bottom start",
                  offset: "5"
                }, {
                  activator: _withCtx$1(({ props }) => [
                    _createVNode$1(_component_v_chip, _mergeProps$1(props, {
                      size: "small",
                      class: "custom-purple-chip font-weight-bold cursor-pointer"
                    }), {
                      default: _withCtx$1(() => [
                        _createTextVNode$1(_toDisplayString$1(selectedYear.value), 1)
                      ]),
                      _: 2
                    }, 1040)
                  ]),
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_list, { density: "compact" }, {
                      default: _withCtx$1(() => [
                        (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(availableYears.value, (year) => {
                          return (_openBlock$1(), _createBlock$1(_component_v_list_item, {
                            key: year,
                            onClick: $event => (selectedYear.value = year),
                            active: selectedYear.value === year,
                            color: "primary"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_v_list_item_title, { class: "text-caption font-weight-medium" }, {
                                default: _withCtx$1(() => [
                                  _createTextVNode$1(_toDisplayString$1(year) + "年", 1)
                                ]),
                                _: 2
                              }, 1024)
                            ]),
                            _: 2
                          }, 1032, ["onClick", "active"]))
                        }), 128))
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }))
              : (_openBlock$1(), _createBlock$1(_component_v_menu, {
                  key: 1,
                  location: "bottom start",
                  offset: "5"
                }, {
                  activator: _withCtx$1(({ props }) => [
                    _createVNode$1(_component_v_chip, _mergeProps$1(props, {
                      size: "small",
                      class: "custom-purple-chip font-weight-bold cursor-pointer"
                    }), {
                      default: _withCtx$1(() => [
                        _createTextVNode$1(_toDisplayString$1(timeRange.value === 'all' ? '全部' : timeRange.value + '天'), 1)
                      ]),
                      _: 2
                    }, 1040)
                  ]),
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_list, { density: "compact" }, {
                      default: _withCtx$1(() => [
                        (_openBlock$1(), _createElementBlock$1(_Fragment$1, null, _renderList$1([{title:'30天', value:'30'}, {title:'90天', value:'90'}, {title:'全部', value:'all'}], (opt) => {
                          return _createVNode$1(_component_v_list_item, {
                            key: opt.value,
                            onClick: $event => (timeRange.value = opt.value),
                            active: timeRange.value === opt.value,
                            color: "primary"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_v_list_item_title, { class: "text-caption font-weight-medium" }, {
                                default: _withCtx$1(() => [
                                  _createTextVNode$1(_toDisplayString$1(opt.title), 1)
                                ]),
                                _: 2
                              }, 1024)
                            ]),
                            _: 2
                          }, 1032, ["onClick", "active"])
                        }), 64))
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }))
          ]),
          (_ctx.$vuetify.display.xs)
            ? (_openBlock$1(), _createBlock$1(_component_v_btn_group, {
                key: 0,
                variant: "tonal",
                density: "compact",
                class: "elevation-0"
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_btn, {
                    color: "primary",
                    size: "small",
                    "min-width": "40",
                    class: "px-0",
                    onClick: _cache[0] || (_cache[0] = $event => (viewMode.value = 'heatmap'))
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, { size: "18" }, {
                        default: _withCtx$1(() => _cache[8] || (_cache[8] = [
                          _createTextVNode$1("mdi-pulse")
                        ])),
                        _: 1,
                        __: [8]
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode$1(_component_v_btn, {
                    color: "primary",
                    size: "small",
                    "min-width": "40",
                    class: "px-0",
                    onClick: _cache[1] || (_cache[1] = $event => (viewMode.value = 'trend'))
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, { size: "18" }, {
                        default: _withCtx$1(() => _cache[9] || (_cache[9] = [
                          _createTextVNode$1("mdi-chart-line")
                        ])),
                        _: 1,
                        __: [9]
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }))
            : (_openBlock$1(), _createElementBlock$1("div", _hoisted_4$1, [
                _createVNode$1(_component_v_btn, {
                  variant: viewMode.value === 'heatmap' ? 'tonal' : 'text',
                  color: viewMode.value === 'heatmap' ? 'primary' : 'default',
                  size: "small",
                  density: "compact",
                  "prepend-icon": "mdi-pulse",
                  class: "view-mode-btn",
                  onClick: _cache[2] || (_cache[2] = $event => (viewMode.value = 'heatmap'))
                }, {
                  default: _withCtx$1(() => _cache[10] || (_cache[10] = [
                    _createTextVNode$1(" 热度日历 ")
                  ])),
                  _: 1,
                  __: [10]
                }, 8, ["variant", "color"]),
                _createVNode$1(_component_v_btn, {
                  variant: viewMode.value === 'trend' ? 'tonal' : 'text',
                  color: viewMode.value === 'trend' ? 'primary' : 'default',
                  size: "small",
                  density: "compact",
                  "prepend-icon": "mdi-chart-line",
                  class: "view-mode-btn",
                  onClick: _cache[3] || (_cache[3] = $event => (viewMode.value = 'trend'))
                }, {
                  default: _withCtx$1(() => _cache[11] || (_cache[11] = [
                    _createTextVNode$1(" 增量趋势 ")
                  ])),
                  _: 1,
                  __: [11]
                }, 8, ["variant", "color"])
              ]))
        ])
      ], 2),
      _createVNode$1(_component_v_card_text, {
        class: _normalizeClass([__props.flat ? 'pa-0 pt-2' : 'pa-2 pa-sm-4 pt-0 main-chart-card-text'])
      }, {
        default: _withCtx$1(() => [
          (loading.value)
            ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_5$1, [
                _createVNode$1(_component_v_progress_circular, {
                  indeterminate: "",
                  color: "primary",
                  size: "40"
                }),
                _cache[12] || (_cache[12] = _createElementVNode$1("span", { class: "text-body-2 text-medium-emphasis ml-3" }, "正在加载分析数据...", -1))
              ]))
            : (_openBlock$1(), _createElementBlock$1("div", _hoisted_6$1, [
                _createElementVNode$1("div", _hoisted_7$1, [
                  _createElementVNode$1("div", _hoisted_8$1, [
                    _createVNode$1(_component_v_avatar, {
                      size: "44",
                      class: "mr-3",
                      style: {"border":"1px solid rgba(0,0,0,0.06)","background":"white"}
                    }, {
                      default: _withCtx$1(() => [
                        (__props.plugin.icon || __props.plugin.plugin_icon || pluginDetailData.value?.plugin_icon)
                          ? (_openBlock$1(), _createBlock$1(_component_v_img, {
                              key: 0,
                              src: __props.plugin.icon || __props.plugin.plugin_icon || pluginDetailData.value?.plugin_icon
                            }, {
                              placeholder: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  size: "24",
                                  color: "primary"
                                }, {
                                  default: _withCtx$1(() => _cache[13] || (_cache[13] = [
                                    _createTextVNode$1("mdi-puzzle-outline")
                                  ])),
                                  _: 1,
                                  __: [13]
                                })
                              ]),
                              _: 1
                            }, 8, ["src"]))
                          : (_openBlock$1(), _createBlock$1(_component_v_icon, {
                              key: 1,
                              size: "24",
                              color: "primary"
                            }, {
                              default: _withCtx$1(() => _cache[14] || (_cache[14] = [
                                _createTextVNode$1("mdi-puzzle-outline")
                              ])),
                              _: 1,
                              __: [14]
                            }))
                      ]),
                      _: 1
                    }),
                    _createElementVNode$1("div", _hoisted_9$1, [
                      _createElementVNode$1("div", _hoisted_10$1, [
                        _createElementVNode$1("span", _hoisted_11$1, _toDisplayString$1(__props.plugin.plugin_name || __props.plugin.name), 1),
                        _createElementVNode$1("span", _hoisted_12$1, "(" + _toDisplayString$1(__props.plugin.plugin_id || __props.plugin.id) + ")", 1)
                      ]),
                      _createElementVNode$1("span", _hoisted_13$1, _toDisplayString$1((pluginDetailData.value?.current_downloads || __props.plugin.downloads || 0).toLocaleString()) + " downloads in " + _toDisplayString$1(selectedYear.value), 1)
                    ])
                  ]),
                  _createVNode$1(_component_v_btn, {
                    size: "small",
                    color: "warning",
                    variant: "outlined",
                    "prepend-icon": "mdi-refresh",
                    onClick: _cache[4] || (_cache[4] = $event => (showResetConfirm.value = true)),
                    loading: resetting.value,
                    class: "custom-reset-btn d-none d-sm-flex"
                  }, {
                    default: _withCtx$1(() => _cache[15] || (_cache[15] = [
                      _createTextVNode$1(" 重置数据 ")
                    ])),
                    _: 1,
                    __: [15]
                  }, 8, ["loading"])
                ]),
                _createElementVNode$1("div", _hoisted_14$1, [
                  _createElementVNode$1("div", _hoisted_15$1, [
                    _createElementVNode$1("div", _hoisted_16$1, _toDisplayString$1((pluginDetailData.value?.current_downloads || __props.plugin.downloads || 0).toLocaleString()), 1),
                    _cache[16] || (_cache[16] = _createElementVNode$1("div", { class: "stats-label" }, "总下载量", -1))
                  ]),
                  _createElementVNode$1("div", _hoisted_17$1, [
                    _createElementVNode$1("div", _hoisted_18$1, _toDisplayString$1(activeDays.value), 1),
                    _cache[17] || (_cache[17] = _createElementVNode$1("div", { class: "stats-label" }, "活跃天数", -1))
                  ]),
                  _createElementVNode$1("div", _hoisted_19$1, [
                    _createElementVNode$1("div", _hoisted_20$1, "+" + _toDisplayString$1(maxDayIncrement.value), 1),
                    _cache[18] || (_cache[18] = _createElementVNode$1("div", { class: "stats-label" }, "最高单日新增", -1))
                  ]),
                  _createElementVNode$1("div", _hoisted_21$1, [
                    _createElementVNode$1("div", _hoisted_22$1, _toDisplayString$1(currentStreak.value) + " 天", 1),
                    _cache[19] || (_cache[19] = _createElementVNode$1("div", { class: "stats-label" }, "连续增长天数", -1))
                  ])
                ]),
                _createElementVNode$1("div", _hoisted_23$1, [
                  (viewMode.value === 'heatmap')
                    ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_24$1, [
                        _createVNode$1(GitHubHeatmap, {
                          api: __props.api,
                          "selected-plugin-id": __props.plugin.plugin_id || __props.plugin.id,
                          "selected-year": selectedYear.value,
                          "onUpdate:selectedYear": _cache[5] || (_cache[5] = $event => ((selectedYear).value = $event)),
                          "hide-stats": true,
                          "hide-header": true,
                          class: "heatmap-fill",
                          ref: "heatmapRef"
                        }, null, 8, ["api", "selected-plugin-id", "selected-year"])
                      ]))
                    : (viewMode.value === 'trend')
                      ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_25$1, [
                          _createVNode$1(TrendChart, {
                            api: __props.api,
                            "plugin-data": pluginDetailData.value,
                            "time-range": timeRange.value,
                            "hide-filter": true,
                            ref: "trendChartRef"
                          }, null, 8, ["api", "plugin-data", "time-range"])
                        ]))
                      : _createCommentVNode$1("", true)
                ])
              ]))
        ]),
        _: 1
      }, 8, ["class"]),
      (_openBlock$1(), _createBlock$1(_Teleport, { to: "body" }, [
        (tooltip.show)
          ? (_openBlock$1(), _createElementBlock$1("div", {
              key: 0,
              class: "heatmap-tooltip",
              style: _normalizeStyle(tooltip.style)
            }, _toDisplayString$1(tooltip.content), 5))
          : _createCommentVNode$1("", true)
      ])),
      _createVNode$1(_component_v_dialog, {
        modelValue: showResetConfirm.value,
        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((showResetConfirm).value = $event)),
        "max-width": "400"
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_card, { class: "heat-glass-card" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_v_card_title, { class: "text-subtitle-1 font-weight-bold d-flex align-center" }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_icon, {
                    color: "warning",
                    class: "mr-2"
                  }, {
                    default: _withCtx$1(() => _cache[20] || (_cache[20] = [
                      _createTextVNode$1("mdi-alert-circle")
                    ])),
                    _: 1,
                    __: [20]
                  }),
                  _cache[21] || (_cache[21] = _createTextVNode$1(" 确认要重置该插件数据吗？ "))
                ]),
                _: 1,
                __: [21]
              }),
              _createVNode$1(_component_v_card_text, { class: "text-body-2 pt-2" }, {
                default: _withCtx$1(() => [
                  _createTextVNode$1(" 此操作将清空插件「" + _toDisplayString$1(__props.plugin.plugin_name || __props.plugin.name) + "」的所有每日监控记录，以当前下载量作为新的计算基准。此操作不可逆。 ", 1)
                ]),
                _: 1
              }),
              _createVNode$1(_component_v_card_actions, { class: "pa-3" }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_spacer),
                  _createVNode$1(_component_v_btn, {
                    size: "small",
                    variant: "outlined",
                    onClick: _cache[6] || (_cache[6] = $event => (showResetConfirm.value = false))
                  }, {
                    default: _withCtx$1(() => _cache[22] || (_cache[22] = [
                      _createTextVNode$1("取消")
                    ])),
                    _: 1,
                    __: [22]
                  }),
                  _createVNode$1(_component_v_btn, {
                    size: "small",
                    color: "error",
                    variant: "flat",
                    onClick: resetPluginData,
                    loading: resetting.value
                  }, {
                    default: _withCtx$1(() => _cache[23] || (_cache[23] = [
                      _createTextVNode$1("确认重置")
                    ])),
                    _: 1,
                    __: [23]
                  }, 8, ["loading"])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"])
    ]),
    _: 1
  }, 8, ["class", "style"]))
}
}

};
const PluginDetail = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-08ec4ee4"]]);

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createBlock:_createBlock,mergeProps:_mergeProps,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "heat-topbar mb-3" };
const _hoisted_2 = { class: "heat-topbar__left" };
const _hoisted_3 = { class: "heat-topbar__icon" };
const _hoisted_4 = { class: "heat-topbar__right" };
const _hoisted_5 = { class: "premium-stat-card__body" };
const _hoisted_6 = { class: "premium-stat-card__info" };
const _hoisted_7 = { class: "premium-stat-card__value text-primary" };
const _hoisted_8 = {
  key: 0,
  class: "stats-panel-skeleton"
};
const _hoisted_9 = { key: 1 };
const _hoisted_10 = { class: "premium-stat-card__icon text-primary d-none d-sm-flex" };
const _hoisted_11 = { class: "premium-stat-card__body" };
const _hoisted_12 = { class: "premium-stat-card__info" };
const _hoisted_13 = { class: "premium-stat-card__value text-success" };
const _hoisted_14 = {
  key: 0,
  class: "stats-panel-skeleton"
};
const _hoisted_15 = { key: 1 };
const _hoisted_16 = { class: "premium-stat-card__icon text-success d-none d-sm-flex" };
const _hoisted_17 = { class: "premium-stat-card__body" };
const _hoisted_18 = { class: "premium-stat-card__info" };
const _hoisted_19 = { class: "premium-stat-card__value text-info" };
const _hoisted_20 = {
  key: 0,
  class: "stats-panel-skeleton"
};
const _hoisted_21 = { key: 1 };
const _hoisted_22 = { class: "premium-stat-card__icon text-info d-none d-sm-flex" };
const _hoisted_23 = { class: "premium-stat-card__body" };
const _hoisted_24 = { class: "premium-stat-card__info" };
const _hoisted_25 = { class: "premium-stat-card__value text-warning" };
const _hoisted_26 = {
  key: 0,
  class: "stats-panel-skeleton"
};
const _hoisted_27 = { key: 1 };
const _hoisted_28 = { class: "premium-stat-card__icon text-warning d-none d-sm-flex" };
const _hoisted_29 = {
  key: 0,
  class: "d-flex justify-center align-center py-12"
};
const _hoisted_30 = { class: "text-center" };
const _hoisted_31 = { class: "pa-2 pa-sm-4 pb-0" };
const _hoisted_32 = { class: "d-flex align-center justify-space-between flex-wrap gap-2 width-100" };
const _hoisted_33 = { class: "d-flex align-center gap-1" };
const _hoisted_34 = { class: "text-subtitle-1 font-weight-bold" };
const _hoisted_35 = {
  key: 0,
  class: "text-center py-8"
};
const _hoisted_36 = { key: 1 };
const {ref,reactive,computed,onMounted,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    required: true
  }
},
  emits: ['switch', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

// State
const loading = ref(true);
const refreshing = ref(false);
const monitoredPlugins = ref([]);
const totalDownloads = ref(0);
const totalGrowth = ref(0);
const lastUpdateTime = ref('');
const selectedPlugin = ref(null);
const sortBy = ref('downloads');
const pluginVersion = ref('');
const running = ref(false);

const pluginDetailRef = ref(null);

const sortOptions = [
  { title: '下载量降序', value: 'downloads' },
  { title: '增量进度降序', value: 'progress' },
  { title: '插件名称', value: 'name' }
];

const currentSortLabel = computed(() => {
  const option = sortOptions.find(opt => opt.value === sortBy.value);
  return option ? option.title : '排序方式'
});

const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
});

// Format helpers
const formattedLastCheck = computed(() => {
  if (!lastUpdateTime.value) return '未知'
  // Clean up timestamp if contains date
  const parts = lastUpdateTime.value.split(' ');
  return parts.length > 1 ? parts[1] : lastUpdateTime.value
});

// Sorting computation
const sortedPlugins = computed(() => {
  const list = [...monitoredPlugins.value];
  if (sortBy.value === 'downloads') {
    return list.sort((a, b) => b.downloads - a.downloads)
  }
  if (sortBy.value === 'progress') {
    return list.sort((a, b) => {
      const progA = (a.increment_since_last || 0) / (a.download_increment || 100);
      const progB = (b.increment_since_last || 0) / (b.download_increment || 100);
      return progB - progA
    })
  }
  if (sortBy.value === 'name') {
    return list.sort((a, b) => (a.plugin_name || a.name || '').localeCompare(b.plugin_name || b.name || ''))
  }
  return list
});

// Notification helper
function showMessage(message, color = 'success') {
  snackbar.message = message;
  snackbar.color = color;
  snackbar.show = true;
}

function goToConfig() {
  emit('switch');
}

// Select plugin for detail visualization
function selectPlugin(plugin) {
  selectedPlugin.value = plugin;
}

// Load status data
async function loadData() {
  try {
    const statusData = await props.api.get('plugin/PluginHeatMonitor/status');
    if (statusData) {
      monitoredPlugins.value = statusData.monitored_plugins || [];
      totalDownloads.value = statusData.total_downloads || 0;
      lastUpdateTime.value = statusData.global_last_check_time || '';
      totalGrowth.value = statusData.total_daily_growth || 0;
      pluginVersion.value = statusData.version || '';

      if (monitoredPlugins.value.length > 0) {
        const stillExists = selectedPlugin.value && monitoredPlugins.value.some(
          p => (p.id || p.plugin_id) === (selectedPlugin.value.id || selectedPlugin.value.plugin_id)
        );
        if (!stillExists) {
          selectedPlugin.value = sortedPlugins.value[0];
        } else {
          const freshPlugin = monitoredPlugins.value.find(
            p => (p.id || p.plugin_id) === (selectedPlugin.value.id || selectedPlugin.value.plugin_id)
          );
          if (freshPlugin) {
            selectedPlugin.value = freshPlugin;
          }
        }
      } else {
        selectedPlugin.value = null;
      }
    }
  } catch (error) {
    console.error('加载监控主页数据失败:', error);
    showMessage('获取服务状态失败', 'error');
  }
}

async function refreshData() {
  refreshing.value = true;
  try {
    await loadData();
    if (pluginDetailRef.value && typeof pluginDetailRef.value.loadDetailData === 'function') {
      await pluginDetailRef.value.loadDetailData();
    }
    showMessage('热度状态已最新');
  } catch (error) {
    showMessage('刷新失败', 'error');
  } finally {
    refreshing.value = false;
  }
}

async function runOnce() {
  running.value = true;
  try {
    const response = await props.api.post('plugin/PluginHeatMonitor/run_once');
    if (response && response.status === 'success') {
      showMessage('已触发立即运行');
      setTimeout(() => {
        refreshData();
      }, 1500);
    } else {
      showMessage(response?.message || '触发失败', 'error');
    }
  } catch (error) {
    console.error('触发立即运行失败:', error);
    showMessage('触发立即运行失败', 'error');
  } finally {
    running.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  await loadData();
  loading.value = false;
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_menu = _resolveComponent("v-menu");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_snackbar = _resolveComponent("v-snackbar");
  const _component_v_container = _resolveComponent("v-container");

  return (_openBlock(), _createBlock(_component_v_container, {
    fluid: "",
    class: "heat-page-container pa-2 pa-sm-4 max-width-xl mx-auto"
  }, {
    default: _withCtx(() => [
      _createElementVNode("div", _hoisted_1, [
        _createElementVNode("div", _hoisted_2, [
          _createElementVNode("div", _hoisted_3, [
            _createVNode(_component_v_icon, { size: "24" }, {
              default: _withCtx(() => _cache[2] || (_cache[2] = [
                _createTextVNode("mdi-chart-timeline-variant")
              ])),
              _: 1,
              __: [2]
            })
          ]),
          _cache[3] || (_cache[3] = _createElementVNode("div", { class: "heat-topbar__meta" }, [
            _createElementVNode("div", { class: "heat-topbar__title" }, "插件热度监控"),
            _createElementVNode("div", { class: "heat-topbar__sub" }, "实时监控已安装插件下载量增量与热度分布")
          ], -1))
        ]),
        _createElementVNode("div", _hoisted_4, [
          _createVNode(_component_v_btn_group, {
            variant: "tonal",
            density: "compact",
            class: "elevation-0"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_btn, {
                color: "primary",
                onClick: refreshData,
                loading: refreshing.value,
                size: "small",
                "min-width": "40",
                class: "px-0 px-sm-3"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_icon, {
                    size: "18",
                    class: "mr-sm-1"
                  }, {
                    default: _withCtx(() => _cache[4] || (_cache[4] = [
                      _createTextVNode("mdi-refresh")
                    ])),
                    _: 1,
                    __: [4]
                  }),
                  _cache[5] || (_cache[5] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "刷新", -1))
                ]),
                _: 1,
                __: [5]
              }, 8, ["loading"]),
              _createVNode(_component_v_btn, {
                color: "primary",
                onClick: goToConfig,
                size: "small",
                "min-width": "40",
                class: "px-0 px-sm-3"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_icon, {
                    size: "18",
                    class: "mr-sm-1"
                  }, {
                    default: _withCtx(() => _cache[6] || (_cache[6] = [
                      _createTextVNode("mdi-cog-outline")
                    ])),
                    _: 1,
                    __: [6]
                  }),
                  _cache[7] || (_cache[7] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "设置", -1))
                ]),
                _: 1,
                __: [7]
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                onClick: _cache[0] || (_cache[0] = $event => (emit('close'))),
                size: "small",
                "min-width": "40",
                class: "px-0 px-sm-3"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_icon, {
                    size: "18",
                    class: "mr-sm-1"
                  }, {
                    default: _withCtx(() => _cache[8] || (_cache[8] = [
                      _createTextVNode("mdi-close")
                    ])),
                    _: 1,
                    __: [8]
                  }),
                  _cache[9] || (_cache[9] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "关闭", -1))
                ]),
                _: 1,
                __: [9]
              })
            ]),
            _: 1
          })
        ])
      ]),
      _createVNode(_component_v_row, { class: "grid-gap-12 mb-1" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_col, {
            cols: "3",
            class: "grid-col-gap-12"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, {
                class: "premium-stat-card card-primary",
                variant: "flat"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_5, [
                    _createElementVNode("div", _hoisted_6, [
                      _cache[11] || (_cache[11] = _createElementVNode("span", { class: "premium-stat-card__label" }, "监控插件", -1)),
                      _createElementVNode("span", _hoisted_7, [
                        (loading.value)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_8))
                          : (_openBlock(), _createElementBlock("span", _hoisted_9, [
                              _createTextVNode(_toDisplayString(monitoredPlugins.value.length) + " ", 1),
                              _cache[10] || (_cache[10] = _createElementVNode("span", { class: "unit-text" }, "个", -1))
                            ]))
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_10, [
                      _createVNode(_component_v_icon, { size: "22" }, {
                        default: _withCtx(() => _cache[12] || (_cache[12] = [
                          _createTextVNode("mdi-puzzle-outline")
                        ])),
                        _: 1,
                        __: [12]
                      })
                    ])
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "3",
            class: "grid-col-gap-12"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, {
                class: "premium-stat-card card-success",
                variant: "flat"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_11, [
                    _createElementVNode("div", _hoisted_12, [
                      _cache[13] || (_cache[13] = _createElementVNode("span", { class: "premium-stat-card__label" }, "总下载量", -1)),
                      _createElementVNode("span", _hoisted_13, [
                        (loading.value)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_14))
                          : (_openBlock(), _createElementBlock("span", _hoisted_15, _toDisplayString(totalDownloads.value.toLocaleString()), 1))
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_16, [
                      _createVNode(_component_v_icon, { size: "22" }, {
                        default: _withCtx(() => _cache[14] || (_cache[14] = [
                          _createTextVNode("mdi-download-outline")
                        ])),
                        _: 1,
                        __: [14]
                      })
                    ])
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "3",
            class: "grid-col-gap-12"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, {
                class: "premium-stat-card card-info",
                variant: "flat"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_17, [
                    _createElementVNode("div", _hoisted_18, [
                      _cache[15] || (_cache[15] = _createElementVNode("span", { class: "premium-stat-card__label" }, "今日新增", -1)),
                      _createElementVNode("span", _hoisted_19, [
                        (loading.value)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_20))
                          : (_openBlock(), _createElementBlock("span", _hoisted_21, "+" + _toDisplayString(totalGrowth.value.toLocaleString()), 1))
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_22, [
                      _createVNode(_component_v_icon, { size: "22" }, {
                        default: _withCtx(() => _cache[16] || (_cache[16] = [
                          _createTextVNode("mdi-trending-up")
                        ])),
                        _: 1,
                        __: [16]
                      })
                    ])
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "3",
            class: "grid-col-gap-12"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card, {
                class: "premium-stat-card card-warning",
                variant: "flat"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_23, [
                    _createElementVNode("div", _hoisted_24, [
                      _cache[17] || (_cache[17] = _createElementVNode("span", { class: "premium-stat-card__label" }, "最近检查", -1)),
                      _createElementVNode("span", _hoisted_25, [
                        (loading.value)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_26))
                          : (_openBlock(), _createElementBlock("span", _hoisted_27, _toDisplayString(formattedLastCheck.value), 1))
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_28, [
                      _createVNode(_component_v_icon, { size: "22" }, {
                        default: _withCtx(() => _cache[18] || (_cache[18] = [
                          _createTextVNode("mdi-clock-outline")
                        ])),
                        _: 1,
                        __: [18]
                      })
                    ])
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      (loading.value)
        ? (_openBlock(), _createElementBlock("div", _hoisted_29, [
            _createElementVNode("div", _hoisted_30, [
              _createVNode(_component_v_progress_circular, {
                indeterminate: "",
                color: "primary",
                size: "48",
                class: "mb-3"
              }),
              _cache[19] || (_cache[19] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "载入数据中，请稍候...", -1))
            ])
          ]))
        : (_openBlock(), _createBlock(_component_v_row, {
            key: 1,
            class: "heat-animate-scale-in grid-gap-12"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_col, {
                cols: "12",
                lg: "8",
                xl: "9",
                class: "grid-col-gap-12"
              }, {
                default: _withCtx(() => [
                  (selectedPlugin.value)
                    ? (_openBlock(), _createBlock(PluginDetail, {
                        key: 0,
                        plugin: selectedPlugin.value,
                        api: __props.api,
                        class: "main-chart-card heat-glass-card",
                        ref_key: "pluginDetailRef",
                        ref: pluginDetailRef,
                        onDataChanged: loadData
                      }, null, 8, ["plugin", "api"]))
                    : _createCommentVNode("", true)
                ]),
                _: 1
              }),
              _createVNode(_component_v_col, {
                cols: "12",
                lg: "4",
                xl: "3",
                class: "grid-col-gap-12"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card, {
                    class: "plugin-sidebar-card heat-glass-card",
                    variant: "flat"
                  }, {
                    default: _withCtx(() => [
                      _createElementVNode("div", _hoisted_31, [
                        _createElementVNode("div", _hoisted_32, [
                          _createElementVNode("div", _hoisted_33, [
                            _createElementVNode("span", _hoisted_34, "已监控 " + _toDisplayString(monitoredPlugins.value.length) + " 个插件", 1)
                          ]),
                          _createVNode(_component_v_menu, { location: "bottom end" }, {
                            activator: _withCtx(({ props }) => [
                              _createVNode(_component_v_btn, _mergeProps({
                                variant: "text",
                                size: "small",
                                color: "primary"
                              }, props, {
                                "prepend-icon": "mdi-sort",
                                class: "px-2 font-weight-bold text-caption"
                              }), {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(currentSortLabel.value), 1)
                                ]),
                                _: 2
                              }, 1040)
                            ]),
                            default: _withCtx(() => [
                              _createVNode(_component_v_list, { density: "compact" }, {
                                default: _withCtx(() => [
                                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(sortOptions, (opt) => {
                                    return _createVNode(_component_v_list_item, {
                                      key: opt.value,
                                      onClick: $event => (sortBy.value = opt.value),
                                      active: sortBy.value === opt.value,
                                      color: "primary"
                                    }, {
                                      default: _withCtx(() => [
                                        _createVNode(_component_v_list_item_title, { class: "text-caption font-weight-medium" }, {
                                          default: _withCtx(() => [
                                            _createTextVNode(_toDisplayString(opt.title), 1)
                                          ]),
                                          _: 2
                                        }, 1024)
                                      ]),
                                      _: 2
                                    }, 1032, ["onClick", "active"])
                                  }), 64))
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ])
                      ]),
                      _createVNode(_component_v_card_text, { class: "pa-2 pa-sm-4 pt-0 plugin-list-scroll" }, {
                        default: _withCtx(() => [
                          (monitoredPlugins.value.length === 0)
                            ? (_openBlock(), _createElementBlock("div", _hoisted_35, [
                                _createVNode(_component_v_icon, {
                                  color: "grey-lighten-1",
                                  size: "36"
                                }, {
                                  default: _withCtx(() => _cache[20] || (_cache[20] = [
                                    _createTextVNode("mdi-puzzle-outline")
                                  ])),
                                  _: 1,
                                  __: [20]
                                }),
                                _cache[22] || (_cache[22] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mt-2" }, "暂无监控插件", -1)),
                                _createVNode(_component_v_btn, {
                                  size: "x-small",
                                  color: "primary",
                                  variant: "text",
                                  class: "mt-1",
                                  onClick: goToConfig
                                }, {
                                  default: _withCtx(() => _cache[21] || (_cache[21] = [
                                    _createTextVNode(" 立即去配置 ")
                                  ])),
                                  _: 1,
                                  __: [21]
                                })
                              ]))
                            : (_openBlock(), _createElementBlock("div", _hoisted_36, [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sortedPlugins.value, (plugin) => {
                                  return (_openBlock(), _createBlock(PluginListItem, {
                                    key: plugin.plugin_id || plugin.id,
                                    plugin: plugin,
                                    "is-active": selectedPlugin.value && (selectedPlugin.value.id || selectedPlugin.value.plugin_id) === (plugin.id || plugin.plugin_id),
                                    onClick: $event => (selectPlugin(plugin))
                                  }, null, 8, ["plugin", "is-active", "onClick"]))
                                }), 128))
                              ]))
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
          })),
      _createVNode(_component_v_row, { class: "grid-gap-12 mt-1" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_col, {
            cols: "12",
            class: "grid-col-gap-12"
          }, {
            default: _withCtx(() => [
              _createVNode(StatusFooter, {
                "last-update-time": lastUpdateTime.value,
                refreshing: refreshing.value,
                version: pluginVersion.value || undefined,
                running: running.value,
                onRunOnce: runOnce
              }, null, 8, ["last-update-time", "refreshing", "version", "running"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_snackbar, {
        modelValue: snackbar.show,
        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((snackbar.show) = $event)),
        color: snackbar.color,
        timeout: 3000
      }, {
        default: _withCtx(() => [
          _createTextVNode(_toDisplayString(snackbar.message), 1)
        ]),
        _: 1
      }, 8, ["modelValue", "color"])
    ]),
    _: 1
  }))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-89dc626e"]]);

export { Page as default };
