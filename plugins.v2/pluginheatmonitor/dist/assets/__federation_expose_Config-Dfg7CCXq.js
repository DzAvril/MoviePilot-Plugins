import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-CRrXaTHX.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,vModelCheckbox:_vModelCheckbox,withDirectives:_withDirectives,openBlock:_openBlock,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass,toDisplayString:_toDisplayString} = await importShared('vue');


const _hoisted_1 = { class: "heatcfg-page" };
const _hoisted_2 = { class: "heatcfg-topbar" };
const _hoisted_3 = { class: "heatcfg-topbar__left" };
const _hoisted_4 = { class: "heatcfg-topbar__icon" };
const _hoisted_5 = { class: "heatcfg-topbar__right" };
const _hoisted_6 = { class: "heatcfg-card" };
const _hoisted_7 = { class: "heatcfg-card__header" };
const _hoisted_8 = { class: "heatcfg-card__title d-flex align-center" };
const _hoisted_9 = { class: "heatcfg-switch-grid" };
const _hoisted_10 = { class: "heatcfg-switch-item__main" };
const _hoisted_11 = { class: "heatcfg-switch-item__icon" };
const _hoisted_12 = {
  class: "heatcfg-switch",
  style: {"--switch-checked-bg":"#8b5cf6"}
};
const _hoisted_13 = { class: "heatcfg-switch__slider" };
const _hoisted_14 = { class: "heatcfg-switch__circle" };
const _hoisted_15 = {
  class: "heatcfg-switch__cross",
  "xml:space": "preserve",
  style: {"enable-background":"new 0 0 512 512"},
  viewBox: "0 0 365.696 365.696",
  y: "0",
  x: "0",
  height: "6",
  width: "6",
  "xmlns:xlink": "http://www.w3.org/1999/xlink",
  version: "1.1",
  xmlns: "http://www.w3.org/2000/svg"
};
const _hoisted_16 = {
  class: "heatcfg-switch__checkmark",
  "xml:space": "preserve",
  style: {"enable-background":"new 0 0 512 512"},
  viewBox: "0 0 24 24",
  y: "0",
  x: "0",
  height: "10",
  width: "10",
  "xmlns:xlink": "http://www.w3.org/1999/xlink",
  version: "1.1",
  xmlns: "http://www.w3.org/2000/svg"
};
const _hoisted_17 = { class: "heatcfg-switch-item__main" };
const _hoisted_18 = { class: "heatcfg-switch-item__icon" };
const _hoisted_19 = {
  class: "heatcfg-switch",
  style: {"--switch-checked-bg":"#10b981"}
};
const _hoisted_20 = { class: "heatcfg-switch__slider" };
const _hoisted_21 = { class: "heatcfg-switch__circle" };
const _hoisted_22 = {
  class: "heatcfg-switch__cross",
  "xml:space": "preserve",
  style: {"enable-background":"new 0 0 512 512"},
  viewBox: "0 0 365.696 365.696",
  y: "0",
  x: "0",
  height: "6",
  width: "6",
  "xmlns:xlink": "http://www.w3.org/1999/xlink",
  version: "1.1",
  xmlns: "http://www.w3.org/2000/svg"
};
const _hoisted_23 = {
  class: "heatcfg-switch__checkmark",
  "xml:space": "preserve",
  style: {"enable-background":"new 0 0 512 512"},
  viewBox: "0 0 24 24",
  y: "0",
  x: "0",
  height: "10",
  width: "10",
  "xmlns:xlink": "http://www.w3.org/1999/xlink",
  version: "1.1",
  xmlns: "http://www.w3.org/2000/svg"
};
const _hoisted_24 = { class: "heatcfg-switch-item__main" };
const _hoisted_25 = { class: "heatcfg-switch-item__icon" };
const _hoisted_26 = {
  class: "heatcfg-switch",
  style: {"--switch-checked-bg":"#3b82f6"}
};
const _hoisted_27 = { class: "heatcfg-switch__slider" };
const _hoisted_28 = { class: "heatcfg-switch__circle" };
const _hoisted_29 = {
  class: "heatcfg-switch__cross",
  "xml:space": "preserve",
  style: {"enable-background":"new 0 0 512 512"},
  viewBox: "0 0 365.696 365.696",
  y: "0",
  x: "0",
  height: "6",
  width: "6",
  "xmlns:xlink": "http://www.w3.org/1999/xlink",
  version: "1.1",
  xmlns: "http://www.w3.org/2000/svg"
};
const _hoisted_30 = {
  class: "heatcfg-switch__checkmark",
  "xml:space": "preserve",
  style: {"enable-background":"new 0 0 512 512"},
  viewBox: "0 0 24 24",
  y: "0",
  x: "0",
  height: "10",
  width: "10",
  "xmlns:xlink": "http://www.w3.org/1999/xlink",
  version: "1.1",
  xmlns: "http://www.w3.org/2000/svg"
};
const _hoisted_31 = { class: "heatcfg-field" };
const _hoisted_32 = { class: "heatcfg-field__header" };
const _hoisted_33 = { class: "heatcfg-field__title-main" };
const _hoisted_34 = { class: "heatcfg-form-grid" };
const _hoisted_35 = { class: "heatcfg-form-item heatcfg-form-item--full" };
const _hoisted_36 = { class: "heatcfg-form-item" };
const _hoisted_37 = { class: "heatcfg-form-item" };
const {ref,reactive,computed,onMounted,watch} = await importShared('vue');




const _sfc_main = {
  __name: 'Config',
  props: {
  api: {
    type: Object,
    required: true
  }
},
  emits: ['switch', 'close', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const config = reactive({
  enabled: false,
  enable_notification: true,
  enable_mcp: true,
  cron: '0 8 * * *',
  download_increment: 100,
  monitored_plugins: []
});

const availablePlugins = ref([]);
const loading = ref(false);
const saving = ref(false);
ref(false);
const loadingPlugins = ref(false);


const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
});



function showMessage(message, color = 'success') {
  snackbar.message = message;
  snackbar.color = color;
  snackbar.show = true;
}

function goToPage() {
  emit('switch');
}



async function loadConfig() {
  loading.value = true;
  try {
    const response = await props.api.get('plugin/PluginHeatMonitor/config');
    if (response && response.status === 'success') {
      Object.assign(config, response.config);
    } else if (response) {
      Object.assign(config, response);
    }
  } catch (error) {
    console.error('加载配置失败:', error);
    showMessage('加载配置失败', 'error');
  } finally {
    loading.value = false;
  }
}

async function loadAvailablePlugins() {
  loadingPlugins.value = true;
  try {
    const response = await props.api.get('plugin/PluginHeatMonitor/plugins');
    if (response && response.status === 'success') {
      availablePlugins.value = response.plugins;
    }
  } catch (error) {
    console.error('加载插件列表失败:', error);
    showMessage('加载插件列表失败', 'error');
  } finally {
    loadingPlugins.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    const configPayload = {
      enabled: config.enabled,
      enable_notification: config.enable_notification,
      enable_mcp: config.enable_mcp,
      cron: config.cron,
      download_increment: config.download_increment,
      selected_plugins: config.monitored_plugins,
      monitored_plugins: {}
    };

    const response = await props.api.post('plugin/PluginHeatMonitor/config', configPayload);
    if (response && response.status === 'success') {
      showMessage('配置保存成功');
      await loadConfig();
      emit('save', configPayload);
    } else {
      showMessage(response?.message || '保存配置失败', 'error');
    }
  } catch (error) {
    console.error('保存配置失败:', error);
    showMessage('保存配置失败', 'error');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  loadConfig();
  loadAvailablePlugins();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("div", _hoisted_4, [
          _createVNode(_component_v_icon, { size: "24" }, {
            default: _withCtx(() => _cache[8] || (_cache[8] = [
              _createTextVNode("mdi-cog-outline")
            ])),
            _: 1,
            __: [8]
          })
        ]),
        _cache[9] || (_cache[9] = _createElementVNode("div", { class: "heatcfg-topbar__meta" }, [
          _createElementVNode("div", { class: "heatcfg-topbar__title" }, "参数与监控配置"),
          _createElementVNode("div", { class: "heatcfg-topbar__sub" }, "设定监控策略、里程碑增量并查看指标详情")
        ], -1))
      ]),
      _createElementVNode("div", _hoisted_5, [
        _createVNode(_component_v_btn_group, {
          variant: "tonal",
          density: "compact",
          class: "elevation-0"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              color: "primary",
              onClick: goToPage,
              size: "small",
              "min-width": "40",
              class: "px-0 px-sm-3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  size: "18",
                  class: "mr-sm-1"
                }, {
                  default: _withCtx(() => _cache[10] || (_cache[10] = [
                    _createTextVNode("mdi-chart-timeline-variant")
                  ])),
                  _: 1,
                  __: [10]
                }),
                _cache[11] || (_cache[11] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "状态页", -1))
              ]),
              _: 1,
              __: [11]
            }),
            _createVNode(_component_v_btn, {
              color: "primary",
              onClick: saveConfig,
              loading: saving.value,
              size: "small",
              "min-width": "40",
              class: "px-0 px-sm-3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  size: "18",
                  class: "mr-sm-1"
                }, {
                  default: _withCtx(() => _cache[12] || (_cache[12] = [
                    _createTextVNode("mdi-content-save-outline")
                  ])),
                  _: 1,
                  __: [12]
                }),
                _cache[13] || (_cache[13] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "保存", -1))
              ]),
              _: 1,
              __: [13]
            }, 8, ["loading"]),
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
                  default: _withCtx(() => _cache[14] || (_cache[14] = [
                    _createTextVNode("mdi-close")
                  ])),
                  _: 1,
                  __: [14]
                }),
                _cache[15] || (_cache[15] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "关闭", -1))
              ]),
              _: 1,
              __: [15]
            })
          ]),
          _: 1
        })
      ])
    ]),
    _createElementVNode("div", _hoisted_6, [
      _createElementVNode("div", _hoisted_7, [
        _createElementVNode("span", _hoisted_8, [
          _createVNode(_component_v_icon, {
            size: "18",
            color: "#8b5cf6",
            class: "mr-1"
          }, {
            default: _withCtx(() => _cache[16] || (_cache[16] = [
              _createTextVNode("mdi-toggle-switch-outline")
            ])),
            _: 1,
            __: [16]
          }),
          _cache[17] || (_cache[17] = _createTextVNode(" 运行状态与开关 "))
        ])
      ]),
      _createElementVNode("div", _hoisted_9, [
        _createElementVNode("div", {
          class: _normalizeClass(["heatcfg-switch-item", { 'heatcfg-switch-item--active': config.enabled }]),
          style: {"--heatcfg-accent":"#8b5cf6"}
        }, [
          _createElementVNode("div", _hoisted_10, [
            _createElementVNode("div", _hoisted_11, [
              _createVNode(_component_v_icon, { size: "18" }, {
                default: _withCtx(() => _cache[18] || (_cache[18] = [
                  _createTextVNode("mdi-power-plug")
                ])),
                _: 1,
                __: [18]
              })
            ]),
            _cache[19] || (_cache[19] = _createElementVNode("div", { class: "heatcfg-switch-item__text" }, [
              _createElementVNode("span", { class: "heatcfg-switch-item__label" }, "启用监控服务"),
              _createElementVNode("span", { class: "heatcfg-switch-item__hint" }, "定时轮询各插件最新下载量")
            ], -1))
          ]),
          _createElementVNode("label", _hoisted_12, [
            _withDirectives(_createElementVNode("input", {
              "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.enabled) = $event)),
              type: "checkbox"
            }, null, 512), [
              [_vModelCheckbox, config.enabled]
            ]),
            _createElementVNode("div", _hoisted_13, [
              _createElementVNode("div", _hoisted_14, [
                (_openBlock(), _createElementBlock("svg", _hoisted_15, _cache[20] || (_cache[20] = [
                  _createElementVNode("g", null, [
                    _createElementVNode("path", {
                      fill: "currentColor",
                      d: "M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0"
                    })
                  ], -1)
                ]))),
                (_openBlock(), _createElementBlock("svg", _hoisted_16, _cache[21] || (_cache[21] = [
                  _createElementVNode("g", { transform: "translate(-0.4, 0.2)" }, [
                    _createElementVNode("path", {
                      fill: "currentColor",
                      d: "M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z"
                    })
                  ], -1)
                ])))
              ])
            ])
          ])
        ], 2),
        _createElementVNode("div", {
          class: _normalizeClass(["heatcfg-switch-item", { 'heatcfg-switch-item--active': config.enable_notification }]),
          style: {"--heatcfg-accent":"#10b981"}
        }, [
          _createElementVNode("div", _hoisted_17, [
            _createElementVNode("div", _hoisted_18, [
              _createVNode(_component_v_icon, { size: "18" }, {
                default: _withCtx(() => _cache[22] || (_cache[22] = [
                  _createTextVNode("mdi-bell-ring-outline")
                ])),
                _: 1,
                __: [22]
              })
            ]),
            _cache[23] || (_cache[23] = _createElementVNode("div", { class: "heatcfg-switch-item__text" }, [
              _createElementVNode("span", { class: "heatcfg-switch-item__label" }, "启用通知提醒"),
              _createElementVNode("span", { class: "heatcfg-switch-item__hint" }, "增量达到设定值时发送通知")
            ], -1))
          ]),
          _createElementVNode("label", _hoisted_19, [
            _withDirectives(_createElementVNode("input", {
              "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enable_notification) = $event)),
              type: "checkbox"
            }, null, 512), [
              [_vModelCheckbox, config.enable_notification]
            ]),
            _createElementVNode("div", _hoisted_20, [
              _createElementVNode("div", _hoisted_21, [
                (_openBlock(), _createElementBlock("svg", _hoisted_22, _cache[24] || (_cache[24] = [
                  _createElementVNode("g", null, [
                    _createElementVNode("path", {
                      fill: "currentColor",
                      d: "M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0"
                    })
                  ], -1)
                ]))),
                (_openBlock(), _createElementBlock("svg", _hoisted_23, _cache[25] || (_cache[25] = [
                  _createElementVNode("g", { transform: "translate(-0.4, 0.2)" }, [
                    _createElementVNode("path", {
                      fill: "currentColor",
                      d: "M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z"
                    })
                  ], -1)
                ])))
              ])
            ])
          ])
        ], 2),
        _createElementVNode("div", {
          class: _normalizeClass(["heatcfg-switch-item", { 'heatcfg-switch-item--active': config.enable_mcp }]),
          style: {"--heatcfg-accent":"#3b82f6"}
        }, [
          _createElementVNode("div", _hoisted_24, [
            _createElementVNode("div", _hoisted_25, [
              _createVNode(_component_v_icon, { size: "18" }, {
                default: _withCtx(() => _cache[26] || (_cache[26] = [
                  _createTextVNode("mdi-robot-outline")
                ])),
                _: 1,
                __: [26]
              })
            ]),
            _cache[27] || (_cache[27] = _createElementVNode("div", { class: "heatcfg-switch-item__text" }, [
              _createElementVNode("span", { class: "heatcfg-switch-item__label" }, "启用 MCP 工具"),
              _createElementVNode("span", { class: "heatcfg-switch-item__hint" }, "注册工具供大模型查询调用")
            ], -1))
          ]),
          _createElementVNode("label", _hoisted_26, [
            _withDirectives(_createElementVNode("input", {
              "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.enable_mcp) = $event)),
              type: "checkbox"
            }, null, 512), [
              [_vModelCheckbox, config.enable_mcp]
            ]),
            _createElementVNode("div", _hoisted_27, [
              _createElementVNode("div", _hoisted_28, [
                (_openBlock(), _createElementBlock("svg", _hoisted_29, _cache[28] || (_cache[28] = [
                  _createElementVNode("g", null, [
                    _createElementVNode("path", {
                      fill: "currentColor",
                      d: "M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0"
                    })
                  ], -1)
                ]))),
                (_openBlock(), _createElementBlock("svg", _hoisted_30, _cache[29] || (_cache[29] = [
                  _createElementVNode("g", { transform: "translate(-0.4, 0.2)" }, [
                    _createElementVNode("path", {
                      fill: "currentColor",
                      d: "M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z"
                    })
                  ], -1)
                ])))
              ])
            ])
          ])
        ], 2)
      ]),
      _cache[35] || (_cache[35] = _createElementVNode("div", { class: "heatcfg-divider" }, null, -1)),
      _createElementVNode("div", _hoisted_31, [
        _createElementVNode("div", _hoisted_32, [
          _createElementVNode("div", _hoisted_33, [
            _createVNode(_component_v_icon, {
              size: "18",
              color: "#3b82f6",
              class: "heatcfg-field__title-icon"
            }, {
              default: _withCtx(() => _cache[30] || (_cache[30] = [
                _createTextVNode("mdi-cog-box")
              ])),
              _: 1,
              __: [30]
            }),
            _cache[31] || (_cache[31] = _createElementVNode("div", { class: "heatcfg-field__title-text" }, [
              _createElementVNode("label", { class: "heatcfg-field__label" }, "策略与监控设置")
            ], -1))
          ])
        ]),
        _createElementVNode("div", _hoisted_34, [
          _createElementVNode("div", _hoisted_35, [
            _createVNode(_component_v_select, {
              modelValue: config.monitored_plugins,
              "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.monitored_plugins) = $event)),
              items: availablePlugins.value,
              label: "被监控插件",
              multiple: "",
              chips: "",
              clearable: "",
              loading: loadingPlugins.value,
              density: "compact",
              variant: "outlined",
              "hide-details": "auto",
              class: "heatcfg-input"
            }, null, 8, ["modelValue", "items", "loading"]),
            _cache[32] || (_cache[32] = _createElementVNode("div", { class: "heatcfg-field-hint" }, "可多选，仅对所选插件进行增量统计", -1))
          ]),
          _createElementVNode("div", _hoisted_36, [
            _createVNode(_component_v_text_field, {
              modelValue: config.cron,
              "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.cron) = $event)),
              label: "定时执行周期 (Cron)",
              placeholder: "0 */1 * * *",
              density: "compact",
              variant: "outlined",
              "hide-details": "auto",
              class: "heatcfg-input"
            }, null, 8, ["modelValue"]),
            _cache[33] || (_cache[33] = _createElementVNode("div", { class: "heatcfg-field-hint" }, "Cron 表达式，默认每小时执行一次", -1))
          ]),
          _createElementVNode("div", _hoisted_37, [
            _createVNode(_component_v_text_field, {
              modelValue: config.download_increment,
              "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.download_increment) = $event)),
              modelModifiers: { number: true },
              label: "下载增量触发阈值",
              type: "number",
              placeholder: "100",
              density: "compact",
              variant: "outlined",
              "hide-details": "auto",
              class: "heatcfg-input"
            }, null, 8, ["modelValue"]),
            _cache[34] || (_cache[34] = _createElementVNode("div", { class: "heatcfg-field-hint" }, "当前下载量与上次记录相比的增长阈值", -1))
          ])
        ])
      ])
    ]),
    _createVNode(_component_v_alert, {
      type: "info",
      variant: "tonal",
      class: "border-sm heatcfg-alert mt-4",
      density: "comfortable"
    }, {
      default: _withCtx(() => _cache[36] || (_cache[36] = [
        _createTextVNode(" 💡 提示：选择要监控的插件并设置下载增量，当插件下载量增长达到设定值时会发送通知。支持监控包括本插件在内的所有已安装插件。 ")
      ])),
      _: 1,
      __: [36]
    }),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: 3000
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(snackbar.message), 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-d5b8f61f"]]);

export { Config as default };
