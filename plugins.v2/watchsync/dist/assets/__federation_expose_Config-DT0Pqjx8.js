import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment,withModifiers:_withModifiers} = await importShared('vue');


const _hoisted_1 = { class: "plugin-config" };
const _hoisted_2 = { key: 0 };
const _hoisted_3 = { class: "text-subtitle-1 font-weight-bold mt-4 mb-2 d-flex align-center" };
const _hoisted_4 = { class: "text-subtitle-2 mb-2" };
const _hoisted_5 = { key: 0 };
const _hoisted_6 = {
  key: 1,
  class: "text-center text-medium-emphasis py-2"
};

const {ref,reactive,computed,onMounted} = await importShared('vue');


// 接收初始配置

const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: Object,
    default: () => {},
  },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

// 表单状态
const form = ref(null);
const isFormValid = ref(true);
const error = ref(null);
const successMessage = ref(null);
const saving = ref(false);

// 数据状态
const embyServers = ref([]);
const serverUsers = ref({});
const loadingUsers = ref({});


// 配置数据，使用默认值和初始配置合并
const defaultConfig = {
  enabled: true,
  sync_movies: true,
  sync_tv: true,
  min_watch_time: 300,
  zspace_poll_enabled: true,
  zspace_poll_interval: 30,
  sync_groups: [],
};

// 合并默认配置和初始配置
const config = reactive({ ...defaultConfig });

// 初始化配置
onMounted(async () => {
  // 加载初始配置
  if (props.initialConfig) {
    Object.keys(props.initialConfig).forEach(key => {
      if (key in config) {
        config[key] = props.initialConfig[key];
      }
    });
  }

  // 加载Emby服务器列表
  await loadEmbyServers();
});

// 自定义事件，用于保存配置
const emit = __emit;

// 加载Emby服务器列表
async function loadEmbyServers() {
  try {
    // 检查props.api是否可用
    if (!props.api) {
      error.value = 'API对象不可用，请检查插件配置';
      return
    }

    if (typeof props.api.get !== 'function') {
      error.value = 'API调用方法不可用';
      return
    }

    const result = await props.api.get('plugin/WatchSync/servers');

    if (result && result.success) {
      embyServers.value = result.data || [];

      // 清除之前的错误信息
      error.value = null;

      if (embyServers.value.length === 0) {
        error.value = '没有找到可用的Emby服务器，请检查MoviePilot的媒体服务器配置';
      } else {
        // 预加载所有服务器的用户列表
        loadAllServerUsers();
      }
    } else {
      error.value = `加载服务器列表失败: ${result?.message || '未知错误'}`;
    }
  } catch (err) {
    error.value = `加载服务器列表失败: ${err.message}`;
  }
}

// 获取服务器用户列表
function getServerUsers(serverName) {
  return serverUsers.value[serverName] || []
}

const hasZspaceInGroups = computed(() => {
  return (config.sync_groups || []).some(group => {
    return (group.users || []).some(user => isZspaceServer(user.server))
  })
});

function isZspaceServer(serverName) {
  if (!serverName) {
    return false
  }
  const server = embyServers.value.find(item => item.name === serverName);
  if (server?.type === 'zspace') {
    return true
  }
  const normalized = String(serverName).toLowerCase();
  return ['zspace', 'zvideo', 'jiyingshi', 'qizhi', '极影视', '极空间'].some(alias => normalized.includes(alias))
}

// 加载所有服务器的用户列表
async function loadAllServerUsers() {
  try {
    // 检查props.api是否可用
    if (!props.api || typeof props.api.get !== 'function') {
      return
    }

    const result = await props.api.get('plugin/WatchSync/users');

    if (result && result.success) {
      const allUsersData = result.data || {};

      // 存储所有服务器的用户数据
      for (const [serverName, userData] of Object.entries(allUsersData)) {
        serverUsers.value[serverName] = userData || [];
      }

      // 清除之前的错误信息
      error.value = null;

    } else {
      error.value = `加载用户列表失败: ${result?.message || '未知错误'}`;
    }
  } catch (err) {
    error.value = `加载用户列表失败: ${err.message}`;
  }
}

// 加载服务器用户列表（兼容旧接口）
async function loadServerUsers(serverName) {
  if (!serverName) {
    return
  }

  if (serverUsers.value[serverName]) {
    return
  }

  loadingUsers.value[serverName] = true;

  try {
    // 如果还没有加载过任何用户数据，先加载所有服务器的用户
    if (Object.keys(serverUsers.value).length === 0) {
      await loadAllServerUsers();
    }
  } catch (err) {
    console.error('加载用户列表失败:', err);
  } finally {
    loadingUsers.value[serverName] = false;
  }
}

// 添加同步组
function addSyncGroup() {
  config.sync_groups.push({
    name: '',
    enabled: true,
    users: []
  });
}

// 删除同步组
function removeSyncGroup(index) {
  config.sync_groups.splice(index, 1);
}

// 添加组内用户
function addGroupUser(groupIndex) {
  if (!config.sync_groups[groupIndex].users) {
    config.sync_groups[groupIndex].users = [];
  }
  config.sync_groups[groupIndex].users.push({
    server: '',
    username: ''
  });
}

// 删除组内用户
function removeGroupUser(groupIndex, userIndex) {
  config.sync_groups[groupIndex].users.splice(userIndex, 1);
}

// 组内用户服务器变更时的处理
function onGroupUserServerChange(groupIndex, userIndex) {
  const user = config.sync_groups[groupIndex].users[userIndex];

  // 清空用户名
  user.username = '';

  if (user.server) {
    // 检查是否已经有缓存的用户数据
    const cachedUsers = getServerUsers(user.server);

    if (cachedUsers.length === 0) {
      loadServerUsers(user.server);
    }
  }
}



// 保存配置
async function saveConfig() {
  if (!isFormValid.value) {
    error.value = '请修正表单错误';
    return
  }

  saving.value = true;
  error.value = null;
  successMessage.value = null;

  try {
    // 发送保存事件
    emit('save', { ...config });
    successMessage.value = '配置保存成功';
  } catch (err) {
    console.error('保存配置失败:', err);
    error.value = err.message || '保存配置失败';
  } finally {
    saving.value = false;
  }
}

// 重置表单
function resetForm() {
  Object.keys(defaultConfig).forEach(key => {
    config[key] = defaultConfig[key];
  });

  if (form.value) {
    form.value.resetValidation();
  }
}

// 通知主应用关闭组件
function notifyClose() {
  emit('close');
}

// 通知主应用切换到统计页面
function notifySwitch() {
  emit('switch');
}

return (_ctx, _cache) => {
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_expand_transition = _resolveComponent("v-expand-transition");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_form = _resolveComponent("v-form");
  const _component_v_card_actions = _resolveComponent("v-card-actions");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_item, null, {
          append: _withCtx(() => [
            _createVNode(_component_v_btn, {
              icon: "",
              color: "primary",
              variant: "text",
              onClick: notifyClose
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, { left: "" }, {
                  default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
                    _createTextVNode("mdi-close", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
                _createTextVNode("观看记录同步配置", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_text, { class: "overflow-y-auto" }, {
          default: _withCtx(() => [
            (error.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "error",
                  class: "mb-4"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(error.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            (successMessage.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 1,
                  type: "success",
                  class: "mb-4"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(successMessage.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_form, {
              ref_key: "form",
              ref: form,
              modelValue: isFormValid.value,
              "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((isFormValid).value = $event)),
              onSubmit: _withModifiers(saveConfig, ["prevent"])
            }, {
              default: _withCtx(() => [
                _cache[20] || (_cache[20] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-bold mt-4 mb-2" }, "基本设置", -1)),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, { cols: "12" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_switch, {
                          modelValue: config.enabled,
                          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.enabled) = $event)),
                          label: "启用观看记录同步",
                          color: "primary",
                          inset: "",
                          hint: "启用后将自动同步用户观看记录",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _cache[21] || (_cache[21] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-bold mt-4 mb-2" }, "同步设置", -1)),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_switch, {
                          modelValue: config.sync_movies,
                          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.sync_movies) = $event)),
                          label: "同步电影观看记录",
                          color: "primary",
                          inset: ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_switch, {
                          modelValue: config.sync_tv,
                          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.sync_tv) = $event)),
                          label: "同步电视剧观看记录",
                          color: "primary",
                          inset: ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.min_watch_time,
                          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.min_watch_time) = $event)),
                          modelModifiers: { number: true },
                          label: "最小观看时长（秒）",
                          variant: "outlined",
                          type: "number",
                          min: "0",
                          hint: "只有观看时长超过此值才会触发同步",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_expand_transition, null, {
                  default: _withCtx(() => [
                    (hasZspaceInGroups.value)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_2, [
                          _cache[10] || (_cache[10] = _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium mt-2 mb-2" }, "极影视同步", -1)),
                          _createVNode(_component_v_alert, {
                            type: "warning",
                            variant: "tonal",
                            class: "mb-4"
                          }, {
                            default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                              _createTextVNode(" 启用极影视 -> Emby 同步会轮询极影视 Emby 适配接口，用于捕获极影视作为播放源时的进度变化。 ", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_row, null, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_col, {
                                cols: "12",
                                md: "6"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_switch, {
                                    modelValue: config.zspace_poll_enabled,
                                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.zspace_poll_enabled) = $event)),
                                    label: "同步极影视观看记录到 Emby",
                                    color: "primary",
                                    inset: "",
                                    hint: "关闭后仍可同步普通 Emby 到极影视，但不会从极影视读取进度",
                                    "persistent-hint": ""
                                  }, null, 8, ["modelValue"])
                                ]),
                                _: 1
                              }),
                              (config.zspace_poll_enabled)
                                ? (_openBlock(), _createBlock(_component_v_col, {
                                    key: 0,
                                    cols: "12",
                                    md: "6"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_text_field, {
                                        modelValue: config.zspace_poll_interval,
                                        "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.zspace_poll_interval) = $event)),
                                        modelModifiers: { number: true },
                                        label: "极影视轮询间隔（秒）",
                                        variant: "outlined",
                                        type: "number",
                                        min: "10",
                                        step: "5",
                                        hint: "建议 30 秒，最低 10 秒",
                                        "persistent-hint": ""
                                      }, null, 8, ["modelValue"])
                                    ]),
                                    _: 1
                                  }))
                                : _createCommentVNode("", true)
                            ]),
                            _: 1
                          })
                        ]))
                      : _createCommentVNode("", true)
                  ]),
                  _: 1
                }),
                _createElementVNode("div", _hoisted_3, [
                  _cache[13] || (_cache[13] = _createElementVNode("span", null, "同步组配置", -1)),
                  _createVNode(_component_v_spacer),
                  _createVNode(_component_v_btn, {
                    color: "primary",
                    size: "small",
                    onClick: addSyncGroup
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_icon, { left: "" }, {
                        default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                          _createTextVNode("mdi-plus", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[12] || (_cache[12] = _createTextVNode(" 添加同步组 ", -1))
                    ]),
                    _: 1
                  })
                ]),
                (config.sync_groups.length === 0)
                  ? (_openBlock(), _createBlock(_component_v_alert, {
                      key: 0,
                      type: "info",
                      class: "mb-4"
                    }, {
                      default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                        _createTextVNode(" 请添加同步组，将需要同步观看记录的用户加入同一个组中。组内任意用户的观看记录都会自动同步到其他所有用户。 ", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.sync_groups, (group, groupIndex) => {
                  return (_openBlock(), _createBlock(_component_v_card, {
                    key: groupIndex,
                    class: "mb-4",
                    variant: "outlined"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_card_text, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_row, { class: "mb-3" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_col, {
                                cols: "12",
                                md: "6"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_text_field, {
                                    modelValue: group.name,
                                    "onUpdate:modelValue": $event => ((group.name) = $event),
                                    label: "同步组名称",
                                    variant: "outlined",
                                    density: "compact",
                                    placeholder: "例如：家庭成员组"
                                  }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode(_component_v_col, {
                                cols: "12",
                                md: "3"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_switch, {
                                    modelValue: group.enabled,
                                    "onUpdate:modelValue": $event => ((group.enabled) = $event),
                                    label: "启用此同步组",
                                    color: "primary",
                                    inset: ""
                                  }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode(_component_v_col, {
                                cols: "12",
                                md: "3",
                                class: "d-flex align-center justify-end"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_btn, {
                                    color: "error",
                                    variant: "outlined",
                                    size: "small",
                                    onClick: $event => (removeSyncGroup(groupIndex))
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_icon, { left: "" }, {
                                        default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                                          _createTextVNode("mdi-delete", -1)
                                        ]))]),
                                        _: 1
                                      }),
                                      _cache[16] || (_cache[16] = _createTextVNode(" 删除组 ", -1))
                                    ]),
                                    _: 1
                                  }, 8, ["onClick"])
                                ]),
                                _: 2
                              }, 1024)
                            ]),
                            _: 2
                          }, 1024),
                          _createElementVNode("div", _hoisted_4, "组内用户 (" + _toDisplayString(group.users?.length || 0) + "个)", 1),
                          (group.users && group.users.length)
                            ? (_openBlock(), _createElementBlock("div", _hoisted_5, [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(group.users, (user, userIndex) => {
                                  return (_openBlock(), _createBlock(_component_v_row, {
                                    key: userIndex,
                                    class: "mb-2"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_col, {
                                        cols: "12",
                                        md: "5"
                                      }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_v_select, {
                                            modelValue: user.server,
                                            "onUpdate:modelValue": [$event => ((user.server) = $event), $event => (onGroupUserServerChange(groupIndex, userIndex))],
                                            items: embyServers.value,
                                            "item-title": "name",
                                            "item-value": "name",
                                            label: "服务器",
                                            variant: "outlined",
                                            density: "compact"
                                          }, null, 8, ["modelValue", "onUpdate:modelValue", "items"])
                                        ]),
                                        _: 2
                                      }, 1024),
                                      _createVNode(_component_v_col, {
                                        cols: "12",
                                        md: "5"
                                      }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_v_select, {
                                            modelValue: user.username,
                                            "onUpdate:modelValue": $event => ((user.username) = $event),
                                            items: getServerUsers(user.server),
                                            "item-title": "name",
                                            "item-value": "name",
                                            label: "用户名",
                                            variant: "outlined",
                                            density: "compact",
                                            loading: loadingUsers.value[user.server],
                                            hint: user.server ? `${getServerUsers(user.server).length} 个用户可选` : '请先选择服务器',
                                            "persistent-hint": ""
                                          }, null, 8, ["modelValue", "onUpdate:modelValue", "items", "loading", "hint"])
                                        ]),
                                        _: 2
                                      }, 1024),
                                      _createVNode(_component_v_col, {
                                        cols: "12",
                                        md: "2",
                                        class: "d-flex align-center"
                                      }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_v_btn, {
                                            color: "error",
                                            variant: "text",
                                            size: "small",
                                            icon: "",
                                            onClick: $event => (removeGroupUser(groupIndex, userIndex))
                                          }, {
                                            default: _withCtx(() => [
                                              _createVNode(_component_v_icon, null, {
                                                default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                                                  _createTextVNode("mdi-delete", -1)
                                                ]))]),
                                                _: 1
                                              })
                                            ]),
                                            _: 1
                                          }, 8, ["onClick"])
                                        ]),
                                        _: 2
                                      }, 1024)
                                    ]),
                                    _: 2
                                  }, 1024))
                                }), 128))
                              ]))
                            : (_openBlock(), _createElementBlock("div", _hoisted_6, " 暂无组内用户 ")),
                          _createVNode(_component_v_btn, {
                            color: "primary",
                            variant: "text",
                            size: "small",
                            onClick: $event => (addGroupUser(groupIndex)),
                            class: "mt-2"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_icon, { left: "" }, {
                                default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                                  _createTextVNode("mdi-account-plus", -1)
                                ]))]),
                                _: 1
                              }),
                              _cache[19] || (_cache[19] = _createTextVNode(" 添加用户 ", -1))
                            ]),
                            _: 1
                          }, 8, ["onClick"])
                        ]),
                        _: 2
                      }, 1024)
                    ]),
                    _: 2
                  }, 1024))
                }), 128)),
                (successMessage.value)
                  ? (_openBlock(), _createBlock(_component_v_alert, {
                      key: 1,
                      type: "success",
                      class: "mb-4"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(successMessage.value), 1)
                      ]),
                      _: 1
                    }))
                  : _createCommentVNode("", true)
              ]),
              _: 1
            }, 8, ["modelValue"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_actions, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              color: "primary",
              onClick: saveConfig,
              loading: saving.value
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, { left: "" }, {
                  default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                    _createTextVNode("mdi-content-save", -1)
                  ]))]),
                  _: 1
                }),
                _cache[23] || (_cache[23] = _createTextVNode(" 保存配置 ", -1))
              ]),
              _: 1
            }, 8, ["loading"]),
            _createVNode(_component_v_btn, {
              color: "secondary",
              onClick: resetForm
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, { left: "" }, {
                  default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                    _createTextVNode("mdi-refresh", -1)
                  ]))]),
                  _: 1
                }),
                _cache[25] || (_cache[25] = _createTextVNode(" 重置 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_btn, {
              color: "primary",
              onClick: notifySwitch
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, { left: "" }, {
                  default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                    _createTextVNode("mdi-chart-line", -1)
                  ]))]),
                  _: 1
                }),
                _cache[27] || (_cache[27] = _createTextVNode(" 查看统计 ", -1))
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
}
}

};

export { _sfc_main as default };
