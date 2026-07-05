import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "dashboard-widget" };
const _hoisted_2 = { class: "dashboard-content" };
const _hoisted_3 = {
  key: 0,
  class: "d-flex justify-center align-center py-4"
};
const _hoisted_4 = { key: 1 };
const _hoisted_5 = { class: "d-flex align-center mb-2" };
const _hoisted_6 = { class: "text-body-2 font-weight-medium" };
const _hoisted_7 = { class: "d-flex justify-space-between align-center mb-3" };
const _hoisted_8 = { class: "text-center" };
const _hoisted_9 = { class: "text-h6 font-weight-bold text-primary" };
const _hoisted_10 = { class: "text-center" };
const _hoisted_11 = { class: "text-h6 font-weight-bold text-info" };
const _hoisted_12 = { class: "text-center" };
const _hoisted_13 = { class: "text-h6 font-weight-bold text-secondary" };
const _hoisted_14 = { class: "d-flex align-center" };
const _hoisted_15 = { class: "text-caption" };
const _hoisted_16 = {
  key: 1,
  class: "text-center text-caption text-medium-emphasis py-2"
};
const _hoisted_17 = {
  key: 0,
  class: "d-flex justify-center align-center py-2"
};
const _hoisted_18 = { key: 1 };
const _hoisted_19 = { class: "d-flex align-center mb-2" };
const _hoisted_20 = { class: "text-body-2 font-weight-medium" };
const _hoisted_21 = { class: "d-flex justify-space-between align-center mb-3" };
const _hoisted_22 = { class: "text-center" };
const _hoisted_23 = { class: "text-h6 font-weight-bold text-primary" };
const _hoisted_24 = { class: "text-center" };
const _hoisted_25 = { class: "text-h6 font-weight-bold text-info" };
const _hoisted_26 = { class: "text-center" };
const _hoisted_27 = { class: "text-h6 font-weight-bold text-secondary" };
const _hoisted_28 = { class: "d-flex align-center" };
const _hoisted_29 = { class: "text-caption" };
const _hoisted_30 = {
  key: 1,
  class: "text-center text-caption text-medium-emphasis py-2"
};

const {ref,computed,onMounted,onUnmounted} = await importShared('vue');


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

// 组件状态
const loading = ref(true);
const stats = ref({
  todayCount: 0,
  successRate: 0,
  activeUsers: 0,
  syncTypes: []
});
const syncRecords = ref([]);
const serviceStatus = ref('running'); // running, stopped, error
let refreshTimer = null;

// 获取状态图标
function getStatusIcon(status) {
  const icons = {
    'success': 'mdi-check',
    'error': 'mdi-alert',
    'pending': 'mdi-clock-outline',
  };
  return icons[status] || 'mdi-help-circle'
}

// 获取状态颜色
function getStatusColor(status) {
  const colors = {
    'success': 'success',
    'error': 'error',
    'pending': 'warning',
  };
  return colors[status] || 'grey'
}

// 获取同步类型图标
function getSyncTypeIcon(syncType) {
  const icons = {
    'playback': 'mdi-play',
    'favorite': 'mdi-heart',
    'not_favorite': 'mdi-heart-outline',
    'played_status': 'mdi-eye',
    'mark_played': 'mdi-eye',
    'mark_unplayed': 'mdi-eye-off-outline'
  };
  return icons[syncType] || 'mdi-sync'
}

// 获取同步类型颜色
function getSyncTypeColor(syncType) {
  const colors = {
    'playback': 'primary',
    'favorite': 'pink',
    'not_favorite': 'grey',
    'played_status': 'grey',
    'mark_played': 'grey',
    'mark_unplayed': 'grey'
  };
  return colors[syncType] || 'grey'
}

// 服务状态相关的计算属性
const serviceStatusIcon = computed(() => {
  const icons = {
    'running': 'mdi-check-circle',
    'stopped': 'mdi-stop-circle',
    'error': 'mdi-alert-circle'
  };
  return icons[serviceStatus.value] || 'mdi-help-circle'
});

const serviceStatusColor = computed(() => {
  const colors = {
    'running': 'success',
    'stopped': 'warning',
    'error': 'error'
  };
  return colors[serviceStatus.value] || 'grey'
});

const serviceStatusText = computed(() => {
  const texts = {
    'running': '同步服务运行中',
    'stopped': '同步服务已停止',
    'error': '同步服务异常'
  };
  return texts[serviceStatus.value] || '状态未知'
});

// 格式化时间
function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;

  if (diff < 60000) { // 1分钟内
    return '刚刚'
  } else if (diff < 3600000) { // 1小时内
    return Math.floor(diff / 60000) + '分钟前'
  } else if (diff < 86400000) { // 1天内
    return Math.floor(diff / 3600000) + '小时前'
  } else {
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
  }
}

// 获取仪表板数据
async function fetchDashboardData() {
  if (!props.allowRefresh) return

  loading.value = true;

  try {
    // 获取统计数据
    await loadDashboardStats();

    // 获取最近同步记录
    await loadDashboardRecords();

  } catch (error) {
    console.error('获取仪表板数据失败:', error);
  } finally {
    loading.value = false;
  }
}

// 加载仪表板统计数据
async function loadDashboardStats() {
  try {
    const result = await props.api.get('plugin/WatchSync/stats');
    if (result && result.success) {
      const data = result.data;
      stats.value = {
        todayCount: data['今日同步次数'] || 0,
        successRate: parseFloat(data['成功率']) || 0,
        activeUsers: data['活跃用户数'] || 0,
        syncTypes: data['同步类型'] || []
      };

      // 根据成功率判断服务状态
      if (stats.value.successRate >= 90) {
        serviceStatus.value = 'running';
      } else if (stats.value.successRate >= 50) {
        serviceStatus.value = 'stopped';
      } else {
        serviceStatus.value = 'error';
      }
    } else {
      // 设置默认值
      stats.value = {
        todayCount: 0,
        successRate: 0,
        activeUsers: 0,
        syncTypes: []
      };
      serviceStatus.value = 'stopped';
    }
  } catch (error) {
    console.error('获取统计数据失败:', error);
    // 设置默认值
    stats.value = {
      todayCount: 0,
      successRate: 0,
      activeUsers: 0,
      syncTypes: []
    };
    serviceStatus.value = 'error';
  }
}

// 加载仪表板同步记录
async function loadDashboardRecords() {
  try {
    const result = await props.api.get('plugin/WatchSync/records?limit=3');
    if (result && result.success) {
      syncRecords.value = result.data || [];
    } else {
      syncRecords.value = [];
    }
  } catch (error) {
    console.error('获取同步记录失败:', error);
    syncRecords.value = [];
  }
}

// 手动刷新数据
async function refreshData() {
  await fetchDashboardData();
}

// 设置定时刷新
function setupRefreshTimer() {
  if (props.allowRefresh) {
    // 每30秒刷新一次
    refreshTimer = setInterval(() => {
      fetchDashboardData();
    }, 30000);
  }
}

// 初始化
onMounted(() => {
  fetchDashboardData();
  setupRefreshTimer();
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
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_avatar = _resolveComponent("v-avatar");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_item = _resolveComponent("v-card-item");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (!__props.config?.attrs?.border)
      ? (_openBlock(), _createBlock(_component_v_card, {
          key: 0,
          flat: ""
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_text, { class: "pa-0" }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_2, [
                  (loading.value)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_3, [
                        _createVNode(_component_v_progress_circular, {
                          indeterminate: "",
                          color: "primary"
                        })
                      ]))
                    : (_openBlock(), _createElementBlock("div", _hoisted_4, [
                        _createElementVNode("div", _hoisted_5, [
                          _createVNode(_component_v_icon, {
                            color: serviceStatusColor.value,
                            size: "small",
                            class: "mr-2"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(serviceStatusIcon.value), 1)
                            ]),
                            _: 1
                          }, 8, ["color"]),
                          _createElementVNode("span", _hoisted_6, _toDisplayString(serviceStatusText.value), 1),
                          _createVNode(_component_v_spacer),
                          _createVNode(_component_v_chip, {
                            color: stats.value.successRate >= 90 ? 'success' : stats.value.successRate >= 70 ? 'warning' : 'error',
                            size: "x-small",
                            variant: "flat"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(stats.value.successRate) + "% ", 1)
                            ]),
                            _: 1
                          }, 8, ["color"])
                        ]),
                        _createElementVNode("div", _hoisted_7, [
                          _createElementVNode("div", _hoisted_8, [
                            _createElementVNode("div", _hoisted_9, _toDisplayString(stats.value.todayCount), 1),
                            _cache[0] || (_cache[0] = _createElementVNode("div", { class: "text-caption" }, "今日同步", -1))
                          ]),
                          _createElementVNode("div", _hoisted_10, [
                            _createElementVNode("div", _hoisted_11, _toDisplayString(stats.value.activeUsers), 1),
                            _cache[1] || (_cache[1] = _createElementVNode("div", { class: "text-caption" }, "活跃用户", -1))
                          ]),
                          _createElementVNode("div", _hoisted_12, [
                            _createElementVNode("div", _hoisted_13, _toDisplayString(stats.value.syncTypes.length), 1),
                            _cache[2] || (_cache[2] = _createElementVNode("div", { class: "text-caption" }, "同步类型", -1))
                          ])
                        ]),
                        (syncRecords.value.length)
                          ? (_openBlock(), _createBlock(_component_v_list, {
                              key: 0,
                              density: "compact",
                              class: "py-0"
                            }, {
                              default: _withCtx(() => [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(syncRecords.value.slice(0, 3), (record, index) => {
                                  return (_openBlock(), _createBlock(_component_v_list_item, { key: index }, {
                                    prepend: _withCtx(() => [
                                      _createElementVNode("div", _hoisted_14, [
                                        _createVNode(_component_v_icon, {
                                          color: getSyncTypeColor(record.sync_type),
                                          size: "x-small",
                                          class: "mr-1"
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode(_toDisplayString(getSyncTypeIcon(record.sync_type)), 1)
                                          ]),
                                          _: 2
                                        }, 1032, ["color"]),
                                        _createVNode(_component_v_avatar, {
                                          color: getStatusColor(record.status),
                                          size: "x-small"
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_v_icon, {
                                              size: "x-small",
                                              color: "white"
                                            }, {
                                              default: _withCtx(() => [
                                                _createTextVNode(_toDisplayString(getStatusIcon(record.status)), 1)
                                              ]),
                                              _: 2
                                            }, 1024)
                                          ]),
                                          _: 2
                                        }, 1032, ["color"])
                                      ])
                                    ]),
                                    append: _withCtx(() => [
                                      _createElementVNode("span", _hoisted_15, _toDisplayString(formatTime(record.timestamp)), 1)
                                    ]),
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_list_item_title, { class: "text-body-2" }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(record.media_name), 1)
                                        ]),
                                        _: 2
                                      }, 1024),
                                      _createVNode(_component_v_list_item_subtitle, { class: "text-caption" }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(record.source_user) + " → " + _toDisplayString(record.target_user), 1)
                                        ]),
                                        _: 2
                                      }, 1024)
                                    ]),
                                    _: 2
                                  }, 1024))
                                }), 128))
                              ]),
                              _: 1
                            }))
                          : (_openBlock(), _createElementBlock("div", _hoisted_16, " 暂无同步记录 "))
                      ]))
                ])
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
      : (_openBlock(), _createBlock(_component_v_card, { key: 1 }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_item, null, {
              append: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  icon: "",
                  size: "x-small",
                  variant: "text",
                  onClick: refreshData
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, { size: "small" }, {
                      default: _withCtx(() => [...(_cache[3] || (_cache[3] = [
                        _createTextVNode("mdi-refresh", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "text-subtitle-1" }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(__props.config?.attrs?.title || '观看记录同步'), 1)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_text, { class: "pt-2" }, {
              default: _withCtx(() => [
                (loading.value)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_17, [
                      _createVNode(_component_v_progress_circular, {
                        indeterminate: "",
                        color: "primary",
                        size: "small"
                      })
                    ]))
                  : (_openBlock(), _createElementBlock("div", _hoisted_18, [
                      _createElementVNode("div", _hoisted_19, [
                        _createVNode(_component_v_icon, {
                          color: serviceStatusColor.value,
                          size: "small",
                          class: "mr-2"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(serviceStatusIcon.value), 1)
                          ]),
                          _: 1
                        }, 8, ["color"]),
                        _createElementVNode("span", _hoisted_20, _toDisplayString(serviceStatusText.value), 1),
                        _createVNode(_component_v_spacer),
                        _createVNode(_component_v_chip, {
                          color: stats.value.successRate >= 90 ? 'success' : stats.value.successRate >= 70 ? 'warning' : 'error',
                          size: "x-small",
                          variant: "flat"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(stats.value.successRate) + "% ", 1)
                          ]),
                          _: 1
                        }, 8, ["color"])
                      ]),
                      _createElementVNode("div", _hoisted_21, [
                        _createElementVNode("div", _hoisted_22, [
                          _createElementVNode("div", _hoisted_23, _toDisplayString(stats.value.todayCount), 1),
                          _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-caption" }, "今日同步", -1))
                        ]),
                        _createElementVNode("div", _hoisted_24, [
                          _createElementVNode("div", _hoisted_25, _toDisplayString(stats.value.activeUsers), 1),
                          _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-caption" }, "活跃用户", -1))
                        ]),
                        _createElementVNode("div", _hoisted_26, [
                          _createElementVNode("div", _hoisted_27, _toDisplayString(stats.value.syncTypes.length), 1),
                          _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-caption" }, "同步类型", -1))
                        ])
                      ]),
                      (syncRecords.value.length)
                        ? (_openBlock(), _createBlock(_component_v_list, {
                            key: 0,
                            density: "compact",
                            class: "py-0"
                          }, {
                            default: _withCtx(() => [
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(syncRecords.value.slice(0, 3), (record, index) => {
                                return (_openBlock(), _createBlock(_component_v_list_item, { key: index }, {
                                  prepend: _withCtx(() => [
                                    _createElementVNode("div", _hoisted_28, [
                                      _createVNode(_component_v_icon, {
                                        color: getSyncTypeColor(record.sync_type),
                                        size: "x-small",
                                        class: "mr-1"
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(getSyncTypeIcon(record.sync_type)), 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["color"]),
                                      _createVNode(_component_v_avatar, {
                                        color: getStatusColor(record.status),
                                        size: "x-small"
                                      }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_v_icon, {
                                            size: "x-small",
                                            color: "white"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(getStatusIcon(record.status)), 1)
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ]),
                                        _: 2
                                      }, 1032, ["color"])
                                    ])
                                  ]),
                                  append: _withCtx(() => [
                                    _createElementVNode("span", _hoisted_29, _toDisplayString(formatTime(record.timestamp)), 1)
                                  ]),
                                  default: _withCtx(() => [
                                    _createVNode(_component_v_list_item_title, { class: "text-body-2" }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(record.media_name), 1)
                                      ]),
                                      _: 2
                                    }, 1024),
                                    _createVNode(_component_v_list_item_subtitle, { class: "text-caption" }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(record.source_user) + " → " + _toDisplayString(record.target_user), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024))
                              }), 128))
                            ]),
                            _: 1
                          }))
                        : (_openBlock(), _createElementBlock("div", _hoisted_30, " 暂无同步记录 "))
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

export { _sfc_main as default };
