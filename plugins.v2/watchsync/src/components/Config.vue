<template>
  <div class="plugin-config">
    <v-card>
      <v-card-item>
        <v-card-title>观看记录同步配置</v-card-title>
        <template #append>
          <v-btn icon color="primary" variant="text" @click="notifyClose">
            <v-icon left>mdi-close</v-icon>
          </v-btn>
        </template>
      </v-card-item>
      <v-card-text class="overflow-y-auto">
        <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
        <v-alert v-if="successMessage" type="success" class="mb-4">{{ successMessage }}</v-alert>



        <v-form ref="form" v-model="isFormValid" @submit.prevent="saveConfig">
          <!-- 基本设置区域 -->
          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">基本设置</div>
          <v-row>
            <v-col cols="12">
              <v-switch
                v-model="config.enabled"
                label="启用观看记录同步"
                color="primary"
                inset
                hint="启用后将自动同步用户观看记录"
                persistent-hint
              ></v-switch>
            </v-col>
          </v-row>

          <!-- 同步设置区域 -->
          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">同步设置</div>
          <v-row>
            <v-col cols="12" md="6">
              <v-switch
                v-model="config.sync_movies"
                label="同步电影观看记录"
                color="primary"
                inset
              ></v-switch>
            </v-col>
            <v-col cols="12" md="6">
              <v-switch
                v-model="config.sync_tv"
                label="同步电视剧观看记录"
                color="primary"
                inset
              ></v-switch>
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="config.min_watch_time"
                label="最小观看时长（秒）"
                variant="outlined"
                type="number"
                min="0"
                hint="只有观看时长超过此值才会触发同步"
                persistent-hint
              ></v-text-field>
            </v-col>
          </v-row>

          <v-expand-transition>
            <div v-if="hasZspaceInGroups">
              <div class="text-subtitle-2 font-weight-medium mt-2 mb-2">极影视同步</div>
              <v-alert type="warning" variant="tonal" class="mb-4">
                启用极影视 -> Emby 同步会轮询极影视 Emby 适配接口，用于捕获极影视作为播放源时的进度变化。
              </v-alert>
              <v-row>
                <v-col cols="12" md="6">
                  <v-switch
                    v-model="config.zspace_poll_enabled"
                    label="同步极影视观看记录到 Emby"
                    color="primary"
                    inset
                    hint="关闭后仍可同步普通 Emby 到极影视，但不会从极影视读取进度"
                    persistent-hint
                  ></v-switch>
                </v-col>
                <v-col v-if="config.zspace_poll_enabled" cols="12" md="6">
                  <v-text-field
                    v-model.number="config.zspace_poll_interval"
                    label="极影视轮询间隔（秒）"
                    variant="outlined"
                    type="number"
                    min="10"
                    step="5"
                    hint="建议 30 秒，最低 10 秒"
                    persistent-hint
                  ></v-text-field>
                </v-col>
              </v-row>
            </div>
          </v-expand-transition>

          <!-- 同步组配置区域 -->
          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2 d-flex align-center">
            <span>同步组配置</span>
            <v-spacer></v-spacer>
            <v-btn color="primary" size="small" @click="addSyncGroup">
              <v-icon left>mdi-plus</v-icon>
              添加同步组
            </v-btn>
          </div>

          <v-alert v-if="config.sync_groups.length === 0" type="info" class="mb-4">
            请添加同步组，将需要同步观看记录的用户加入同一个组中。组内任意用户的观看记录都会自动同步到其他所有用户。
          </v-alert>

          <v-card v-for="(group, groupIndex) in config.sync_groups" :key="groupIndex" class="mb-4" variant="outlined">
            <v-card-text>
              <!-- 同步组基本信息 -->
              <v-row class="mb-3">
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="group.name"
                    label="同步组名称"
                    variant="outlined"
                    density="compact"
                    placeholder="例如：家庭成员组"
                  ></v-text-field>
                </v-col>
                <v-col cols="12" md="3">
                  <v-switch
                    v-model="group.enabled"
                    label="启用此同步组"
                    color="primary"
                    inset
                  ></v-switch>
                </v-col>
                <v-col cols="12" md="3" class="d-flex align-center justify-end">

                  <v-btn
                    color="error"
                    variant="outlined"
                    size="small"
                    @click="removeSyncGroup(groupIndex)"
                  >
                    <v-icon left>mdi-delete</v-icon>
                    删除组
                  </v-btn>
                </v-col>
              </v-row>

              <!-- 组内用户列表 -->
              <div class="text-subtitle-2 mb-2">组内用户 ({{ group.users?.length || 0 }}个)</div>
              <div v-if="group.users && group.users.length">
                <v-row v-for="(user, userIndex) in group.users" :key="userIndex" class="mb-2">
                  <v-col cols="12" md="5">
                    <v-select
                      v-model="user.server"
                      :items="embyServers"
                      item-title="name"
                      item-value="name"
                      label="服务器"
                      variant="outlined"
                      density="compact"
                      @update:model-value="onGroupUserServerChange(groupIndex, userIndex)"
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="5">
                    <v-select
                      v-model="user.username"
                      :items="getServerUsers(user.server)"
                      item-title="name"
                      item-value="name"
                      label="用户名"
                      variant="outlined"
                      density="compact"
                      :loading="loadingUsers[user.server]"
                      :hint="user.server ? `${getServerUsers(user.server).length} 个用户可选` : '请先选择服务器'"
                      persistent-hint
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="2" class="d-flex align-center">
                    <v-btn
                      color="error"
                      variant="text"
                      size="small"
                      icon
                      @click="removeGroupUser(groupIndex, userIndex)"
                    >
                      <v-icon>mdi-delete</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </div>
              <div v-else class="text-center text-medium-emphasis py-2">
                暂无组内用户
              </div>
              <v-btn
                color="primary"
                variant="text"
                size="small"
                @click="addGroupUser(groupIndex)"
                class="mt-2"
              >
                <v-icon left>mdi-account-plus</v-icon>
                添加用户
              </v-btn>
            </v-card-text>
          </v-card>

          <!-- 成功消息 -->
          <v-alert v-if="successMessage" type="success" class="mb-4">{{ successMessage }}</v-alert>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" @click="saveConfig" :loading="saving">
          <v-icon left>mdi-content-save</v-icon>
          保存配置
        </v-btn>
        <v-btn color="secondary" @click="resetForm">
          <v-icon left>mdi-refresh</v-icon>
          重置
        </v-btn>
        <v-spacer></v-spacer>
        <v-btn color="primary" @click="notifySwitch">
          <v-icon left>mdi-chart-line</v-icon>
          查看统计
        </v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'

// 接收初始配置
const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: Object,
    default: () => {},
  },
})

// 表单状态
const form = ref(null)
const isFormValid = ref(true)
const error = ref(null)
const successMessage = ref(null)
const saving = ref(false)

// 数据状态
const embyServers = ref([])
const serverUsers = ref({})
const loadingUsers = ref({})


// 配置数据，使用默认值和初始配置合并
const defaultConfig = {
  enabled: true,
  sync_movies: true,
  sync_tv: true,
  min_watch_time: 300,
  zspace_poll_enabled: true,
  zspace_poll_interval: 30,
  sync_groups: [],
}

// 合并默认配置和初始配置
const config = reactive({ ...defaultConfig })

// 初始化配置
onMounted(async () => {
  // 加载初始配置
  if (props.initialConfig) {
    Object.keys(props.initialConfig).forEach(key => {
      if (key in config) {
        config[key] = props.initialConfig[key]
      }
    })
  }

  // 加载Emby服务器列表
  await loadEmbyServers()
})

// 自定义事件，用于保存配置
const emit = defineEmits(['save', 'close', 'switch'])

// 加载Emby服务器列表
async function loadEmbyServers() {
  try {
    // 检查props.api是否可用
    if (!props.api) {
      error.value = 'API对象不可用，请检查插件配置'
      return
    }

    if (typeof props.api.get !== 'function') {
      error.value = 'API调用方法不可用'
      return
    }

    const result = await props.api.get('plugin/WatchSync/servers')

    if (result && result.success) {
      embyServers.value = result.data || []

      // 清除之前的错误信息
      error.value = null

      if (embyServers.value.length === 0) {
        error.value = '没有找到可用的Emby服务器，请检查MoviePilot的媒体服务器配置'
      } else {
        // 预加载所有服务器的用户列表
        loadAllServerUsers()
      }
    } else {
      error.value = `加载服务器列表失败: ${result?.message || '未知错误'}`
    }
  } catch (err) {
    error.value = `加载服务器列表失败: ${err.message}`
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
})

function isZspaceServer(serverName) {
  if (!serverName) {
    return false
  }
  const server = embyServers.value.find(item => item.name === serverName)
  if (server?.type === 'zspace') {
    return true
  }
  const normalized = String(serverName).toLowerCase()
  return ['zspace', 'zvideo', 'jiyingshi', 'qizhi', '极影视', '极空间'].some(alias => normalized.includes(alias))
}

// 加载所有服务器的用户列表
async function loadAllServerUsers() {
  try {
    // 检查props.api是否可用
    if (!props.api || typeof props.api.get !== 'function') {
      return
    }

    const result = await props.api.get('plugin/WatchSync/users')

    if (result && result.success) {
      const allUsersData = result.data || {}

      // 存储所有服务器的用户数据
      for (const [serverName, userData] of Object.entries(allUsersData)) {
        serverUsers.value[serverName] = userData || []
      }

      // 清除之前的错误信息
      error.value = null

    } else {
      error.value = `加载用户列表失败: ${result?.message || '未知错误'}`
    }
  } catch (err) {
    error.value = `加载用户列表失败: ${err.message}`
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

  loadingUsers.value[serverName] = true

  try {
    // 如果还没有加载过任何用户数据，先加载所有服务器的用户
    if (Object.keys(serverUsers.value).length === 0) {
      await loadAllServerUsers()
    }
  } catch (err) {
    console.error('加载用户列表失败:', err)
  } finally {
    loadingUsers.value[serverName] = false
  }
}

// 添加同步组
function addSyncGroup() {
  config.sync_groups.push({
    name: '',
    enabled: true,
    users: []
  })
}

// 删除同步组
function removeSyncGroup(index) {
  config.sync_groups.splice(index, 1)
}

// 添加组内用户
function addGroupUser(groupIndex) {
  if (!config.sync_groups[groupIndex].users) {
    config.sync_groups[groupIndex].users = []
  }
  config.sync_groups[groupIndex].users.push({
    server: '',
    username: ''
  })
}

// 删除组内用户
function removeGroupUser(groupIndex, userIndex) {
  config.sync_groups[groupIndex].users.splice(userIndex, 1)
}

// 组内用户服务器变更时的处理
function onGroupUserServerChange(groupIndex, userIndex) {
  const user = config.sync_groups[groupIndex].users[userIndex]

  // 清空用户名
  user.username = ''

  if (user.server) {
    // 检查是否已经有缓存的用户数据
    const cachedUsers = getServerUsers(user.server)

    if (cachedUsers.length === 0) {
      loadServerUsers(user.server)
    }
  }
}



// 保存配置
async function saveConfig() {
  if (!isFormValid.value) {
    error.value = '请修正表单错误'
    return
  }

  saving.value = true
  error.value = null
  successMessage.value = null

  try {
    // 发送保存事件
    emit('save', { ...config })
    successMessage.value = '配置保存成功'
  } catch (err) {
    console.error('保存配置失败:', err)
    error.value = err.message || '保存配置失败'
  } finally {
    saving.value = false
  }
}

// 重置表单
function resetForm() {
  Object.keys(defaultConfig).forEach(key => {
    config[key] = defaultConfig[key]
  })

  if (form.value) {
    form.value.resetValidation()
  }
}

// 通知主应用关闭组件
function notifyClose() {
  emit('close')
}

// 通知主应用切换到统计页面
function notifySwitch() {
  emit('switch')
}
</script>
