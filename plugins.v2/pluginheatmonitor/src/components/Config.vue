<template>
  <div class="heatcfg-page">
    <!-- Topbar -->
    <div class="heatcfg-topbar">
      <div class="heatcfg-topbar__left">
        <div class="heatcfg-topbar__icon">
          <v-icon size="24">mdi-cog-outline</v-icon>
        </div>
        <div class="heatcfg-topbar__meta">
          <div class="heatcfg-topbar__title">参数与监控配置</div>
          <div class="heatcfg-topbar__sub">设定监控策略、里程碑增量并查看指标详情</div>
        </div>
      </div>
      <div class="heatcfg-topbar__right">
        <v-btn-group variant="tonal" density="compact" class="elevation-0">
          <v-btn color="primary" @click="goToPage" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon size="18" class="mr-sm-1">mdi-chart-timeline-variant</v-icon>
            <span class="btn-text d-none d-sm-inline">状态页</span>
          </v-btn>
          <v-btn color="primary" @click="saveConfig" :loading="saving" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon size="18" class="mr-sm-1">mdi-content-save-outline</v-icon>
            <span class="btn-text d-none d-sm-inline">保存</span>
          </v-btn>
          <v-btn color="primary" @click="emit('close')" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon size="18" class="mr-sm-1">mdi-close</v-icon>
            <span class="btn-text d-none d-sm-inline">关闭</span>
          </v-btn>
        </v-btn-group>
      </div>
    </div>



    <!-- Config Card -->
    <div class="heatcfg-card">
      <div class="heatcfg-card__header">
        <span class="heatcfg-card__title d-flex align-center">
          <v-icon size="18" color="#8b5cf6" class="mr-1">mdi-toggle-switch-outline</v-icon>
          运行状态与开关
        </span>
      </div>

      <div class="heatcfg-switch-grid">
        <!-- Switch 1: Enabled -->
        <div
          class="heatcfg-switch-item"
          :class="{ 'heatcfg-switch-item--active': config.enabled }"
          style="--heatcfg-accent: #8b5cf6"
        >
          <div class="heatcfg-switch-item__main">
            <div class="heatcfg-switch-item__icon">
              <v-icon size="18">mdi-power-plug</v-icon>
            </div>
            <div class="heatcfg-switch-item__text">
              <span class="heatcfg-switch-item__label">启用监控服务</span>
              <span class="heatcfg-switch-item__hint">定时轮询各插件最新下载量</span>
            </div>
          </div>
          <label class="heatcfg-switch" style="--switch-checked-bg: #8b5cf6;">
            <input v-model="config.enabled" type="checkbox" />
            <div class="heatcfg-switch__slider">
              <div class="heatcfg-switch__circle">
                <svg
                  class="heatcfg-switch__cross"
                  xml:space="preserve"
                  style="enable-background:new 0 0 512 512"
                  viewBox="0 0 365.696 365.696"
                  y="0"
                  x="0"
                  height="6"
                  width="6"
                  xmlns:xlink="http://www.w3.org/1999/xlink"
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                ><g><path fill="currentColor" d="M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0" /></g></svg>
                <svg
                  class="heatcfg-switch__checkmark"
                  xml:space="preserve"
                  style="enable-background:new 0 0 512 512"
                  viewBox="0 0 24 24"
                  y="0"
                  x="0"
                  height="10"
                  width="10"
                  xmlns:xlink="http://www.w3.org/1999/xlink"
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                ><g transform="translate(-0.4, 0.2)"><path fill="currentColor" d="M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z" /></g></svg>
              </div>
            </div>
          </label>
        </div>

        <!-- Switch 2: Notifications -->
        <div
          class="heatcfg-switch-item"
          :class="{ 'heatcfg-switch-item--active': config.enable_notification }"
          style="--heatcfg-accent: #10b981"
        >
          <div class="heatcfg-switch-item__main">
            <div class="heatcfg-switch-item__icon">
              <v-icon size="18">mdi-bell-ring-outline</v-icon>
            </div>
            <div class="heatcfg-switch-item__text">
              <span class="heatcfg-switch-item__label">启用通知提醒</span>
              <span class="heatcfg-switch-item__hint">增量达到设定值时发送通知</span>
            </div>
          </div>
          <label class="heatcfg-switch" style="--switch-checked-bg: #10b981;">
            <input v-model="config.enable_notification" type="checkbox" />
            <div class="heatcfg-switch__slider">
              <div class="heatcfg-switch__circle">
                <svg
                  class="heatcfg-switch__cross"
                  xml:space="preserve"
                  style="enable-background:new 0 0 512 512"
                  viewBox="0 0 365.696 365.696"
                  y="0"
                  x="0"
                  height="6"
                  width="6"
                  xmlns:xlink="http://www.w3.org/1999/xlink"
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                ><g><path fill="currentColor" d="M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0" /></g></svg>
                <svg
                  class="heatcfg-switch__checkmark"
                  xml:space="preserve"
                  style="enable-background:new 0 0 512 512"
                  viewBox="0 0 24 24"
                  y="0"
                  x="0"
                  height="10"
                  width="10"
                  xmlns:xlink="http://www.w3.org/1999/xlink"
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                ><g transform="translate(-0.4, 0.2)"><path fill="currentColor" d="M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z" /></g></svg>
              </div>
            </div>
          </label>
        </div>

        <!-- Switch 3: MCP -->
        <div
          class="heatcfg-switch-item"
          :class="{ 'heatcfg-switch-item--active': config.enable_mcp }"
          style="--heatcfg-accent: #3b82f6"
        >
          <div class="heatcfg-switch-item__main">
            <div class="heatcfg-switch-item__icon">
              <v-icon size="18">mdi-robot-outline</v-icon>
            </div>
            <div class="heatcfg-switch-item__text">
              <span class="heatcfg-switch-item__label">启用 MCP 工具</span>
              <span class="heatcfg-switch-item__hint">注册工具供大模型查询调用</span>
            </div>
          </div>
          <label class="heatcfg-switch" style="--switch-checked-bg: #3b82f6;">
            <input v-model="config.enable_mcp" type="checkbox" />
            <div class="heatcfg-switch__slider">
              <div class="heatcfg-switch__circle">
                <svg
                  class="heatcfg-switch__cross"
                  xml:space="preserve"
                  style="enable-background:new 0 0 512 512"
                  viewBox="0 0 365.696 365.696"
                  y="0"
                  x="0"
                  height="6"
                  width="6"
                  xmlns:xlink="http://www.w3.org/1999/xlink"
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                ><g><path fill="currentColor" d="M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0" /></g></svg>
                <svg
                  class="heatcfg-switch__checkmark"
                  xml:space="preserve"
                  style="enable-background:new 0 0 512 512"
                  viewBox="0 0 24 24"
                  y="0"
                  x="0"
                  height="10"
                  width="10"
                  xmlns:xlink="http://www.w3.org/1999/xlink"
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                ><g transform="translate(-0.4, 0.2)"><path fill="currentColor" d="M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z" /></g></svg>
              </div>
            </div>
          </label>
        </div>
      </div>

      <div class="heatcfg-divider" />

      <!-- Inputs Section -->
      <div class="heatcfg-field">
        <div class="heatcfg-field__header">
          <div class="heatcfg-field__title-main">
            <v-icon size="18" color="#3b82f6" class="heatcfg-field__title-icon">mdi-cog-box</v-icon>
            <div class="heatcfg-field__title-text">
              <label class="heatcfg-field__label">策略与监控设置</label>
            </div>
          </div>
        </div>

        <div class="heatcfg-form-grid">
          <div class="heatcfg-form-item heatcfg-form-item--full">
            <v-select
              v-model="config.monitored_plugins"
              :items="availablePlugins"
              label="被监控插件"
              multiple
              chips
              clearable
              :loading="loadingPlugins"
              density="compact"
              variant="outlined"
              hide-details="auto"
              class="heatcfg-input"
            />
            <div class="heatcfg-field-hint">可多选，仅对所选插件进行增量统计</div>
          </div>

          <div class="heatcfg-form-item">
            <v-text-field
              v-model="config.cron"
              label="定时执行周期 (Cron)"
              placeholder="0 */1 * * *"
              density="compact"
              variant="outlined"
              hide-details="auto"
              class="heatcfg-input"
            />
            <div class="heatcfg-field-hint">Cron 表达式，默认每小时执行一次</div>
          </div>

          <div class="heatcfg-form-item">
            <v-text-field
              v-model.number="config.download_increment"
              label="下载增量触发阈值"
              type="number"
              placeholder="100"
              density="compact"
              variant="outlined"
              hide-details="auto"
              class="heatcfg-input"
            />
            <div class="heatcfg-field-hint">当前下载量与上次记录相比的增长阈值</div>
          </div>
        </div>
      </div>


    </div>

    <!-- Info Alert -->
    <v-alert
      type="info"
      variant="tonal"
      class="border-sm heatcfg-alert mt-4"
      density="comfortable"
    >
      💡 提示：选择要监控的插件并设置下载增量，当插件下载量增长达到设定值时会发送通知。支持监控包括本插件在内的所有已安装插件。
    </v-alert>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import '../styles/tokens.css'
import { ref, reactive, computed, onMounted, watch } from 'vue'


const props = defineProps({
  api: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['switch', 'close', 'save'])

const config = reactive({
  enabled: false,
  enable_notification: true,
  enable_mcp: true,
  cron: '0 8 * * *',
  download_increment: 100,
  monitored_plugins: []
})

const availablePlugins = ref([])
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const loadingPlugins = ref(false)


const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})



// Helper to extract a display name
function getPluginName(pId) {
  const p = availablePlugins.value.find(item => item.value === pId)
  if (!p) return pId
  // Remove description suffix if exists
  return p.title.split(' ')[0]
}



function showMessage(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function goToPage() {
  emit('switch')
}



async function loadConfig() {
  loading.value = true
  try {
    const response = await props.api.get('plugin/PluginHeatMonitor/config')
    if (response && response.status === 'success') {
      Object.assign(config, response.config)
    } else if (response) {
      Object.assign(config, response)
    }
  } catch (error) {
    console.error('加载配置失败:', error)
    showMessage('加载配置失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadAvailablePlugins() {
  loadingPlugins.value = true
  try {
    const response = await props.api.get('plugin/PluginHeatMonitor/plugins')
    if (response && response.status === 'success') {
      availablePlugins.value = response.plugins
    }
  } catch (error) {
    console.error('加载插件列表失败:', error)
    showMessage('加载插件列表失败', 'error')
  } finally {
    loadingPlugins.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const configPayload = {
      enabled: config.enabled,
      enable_notification: config.enable_notification,
      enable_mcp: config.enable_mcp,
      cron: config.cron,
      download_increment: config.download_increment,
      selected_plugins: config.monitored_plugins,
      monitored_plugins: {}
    }

    const response = await props.api.post('plugin/PluginHeatMonitor/config', configPayload)
    if (response && response.status === 'success') {
      showMessage('配置保存成功')
      await loadConfig()
      emit('save', configPayload)
    } else {
      showMessage(response?.message || '保存配置失败', 'error')
    }
  } catch (error) {
    console.error('保存配置失败:', error)
    showMessage('保存配置失败', 'error')
  } finally {
    saving.value = false
  }
}

async function runOnce() {
  running.value = true
  try {
    const response = await props.api.post('plugin/PluginHeatMonitor/run_once')
    if (response && response.status === 'success') {
      showMessage('已触发立即运行')
    } else {
      showMessage(response?.message || '触发失败', 'error')
    }
  } catch (error) {
    console.error('触发立即运行失败:', error)
    showMessage('触发立即运行失败', 'error')
  } finally {
    running.value = false
  }
}

onMounted(() => {
  loadConfig()
  loadAvailablePlugins()
})
</script>

<style scoped>
.heatcfg-page {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 400px;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', sans-serif;
  -webkit-font-smoothing: antialiased;
  color: rgba(var(--v-theme-on-surface), 0.85);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
}

.heatcfg-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 8px;
}

.heatcfg-topbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.heatcfg-topbar__meta {
  min-width: 0;
  flex: 1;
}

.heatcfg-topbar__right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.heatcfg-topbar__icon {
  width: 42px;
  height: 42px;
  border-radius: 11px;
  background: rgba(139, 92, 246, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8b5cf6;
  flex-shrink: 0;
}

.heatcfg-topbar__title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.3px;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.heatcfg-topbar__sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.heatcfg-alert {
  border-radius: 14px;
}

.heatcfg-card {
  background: rgba(var(--v-theme-on-surface), 0.03);
  backdrop-filter: blur(20px) saturate(150%);
  border-radius: 14px;
  border: 0.5px solid rgba(var(--v-theme-on-surface), 0.08);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.heatcfg-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.heatcfg-card__title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.heatcfg-divider {
  height: 0.5px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  margin: 0 -4px;
}

.heatcfg-field {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.heatcfg-switch-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.heatcfg-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.heatcfg-form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.heatcfg-form-item--full {
  grid-column: span 2;
}

.heatcfg-field__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.heatcfg-field__title-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.heatcfg-field__title-icon {
  flex-shrink: 0;
}

.heatcfg-field__title-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.heatcfg-field__label {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.heatcfg-switch-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 14px;
  background: rgba(var(--v-theme-surface), 0.78);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.heatcfg-switch-item--active {
  border-color: color-mix(in srgb, var(--heatcfg-accent) 45%, transparent);
  background: color-mix(in srgb, var(--heatcfg-accent) 7%, rgba(var(--v-theme-surface), 0.9));
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06), inset 0 0 0 1px color-mix(in srgb, var(--heatcfg-accent) 18%, transparent);
}

.heatcfg-switch-item__main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.heatcfg-switch-item__icon {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--heatcfg-accent);
  background: color-mix(in srgb, var(--heatcfg-accent) 14%, transparent);
}

.heatcfg-switch-grid .heatcfg-switch-item {
  padding: 14px 16px;
}

.heatcfg-switch-grid .heatcfg-switch-item:last-child {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.heatcfg-switch-item:last-child {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding-bottom: 14px;
}

.heatcfg-switch-item__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.heatcfg-switch-item__label {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.84);
}

.heatcfg-switch-item__hint,
.heatcfg-field-hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  line-height: 1.5;
}

.heatcfg-switch {
  --switch-width: 36px;
  --switch-height: 20px;
  --switch-bg: rgba(var(--v-theme-on-surface), 0.22);
  --switch-checked-bg: rgb(var(--v-theme-primary));
  --switch-offset: calc((var(--switch-height) - var(--circle-diameter)) / 2);
  --switch-transition: all 0.2s cubic-bezier(0.27, 0.2, 0.25, 1.51);
  --circle-diameter: 16px;
  --circle-bg: #fff;
  --circle-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
  --circle-checked-shadow: -1px 1px 2px rgba(0, 0, 0, 0.2);
  --circle-transition: var(--switch-transition);
  --icon-transition: all 0.2s cubic-bezier(0.27, 0.2, 0.25, 1.51);
  --icon-cross-color: rgba(0, 0, 0, 0.4);
  --icon-cross-size: 6px;
  --icon-checkmark-color: var(--switch-checked-bg);
  --icon-checkmark-size: 10px;
  --effect-width: calc(var(--circle-diameter) / 2);
  --effect-height: calc(var(--effect-width) / 2 - 1px);
  --effect-bg: var(--circle-bg);
  --effect-border-radius: 1px;
  --effect-transition: all 0.2s ease-in-out;
  display: inline-block;
  flex-shrink: 0;
  user-select: none;
}

.heatcfg-switch input {
  display: none;
}

.heatcfg-switch svg {
  transition: var(--icon-transition);
  position: absolute;
  height: auto;
}

.heatcfg-switch__checkmark {
  width: var(--icon-checkmark-size);
  color: var(--icon-checkmark-color);
  transform: scale(0);
}

.heatcfg-switch__cross {
  width: var(--icon-cross-size);
  color: var(--icon-cross-color);
}

.heatcfg-switch__slider {
  box-sizing: border-box;
  width: var(--switch-width);
  height: var(--switch-height);
  background: var(--switch-bg);
  border-radius: 999px;
  display: flex;
  align-items: center;
  position: relative;
  transition: var(--switch-transition);
  cursor: pointer;
}

.heatcfg-switch__circle {
  width: var(--circle-diameter);
  height: var(--circle-diameter);
  background: var(--circle-bg);
  border-radius: inherit;
  box-shadow: var(--circle-shadow);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--circle-transition);
  z-index: 1;
  position: absolute;
  left: var(--switch-offset);
}

.heatcfg-switch__slider::before {
  content: "";
  position: absolute;
  width: var(--effect-width);
  height: var(--effect-height);
  left: calc(var(--switch-offset) + (var(--effect-width) / 2));
  background: var(--effect-bg);
  border-radius: var(--effect-border-radius);
  transition: var(--effect-transition);
}

.heatcfg-switch input:checked + .heatcfg-switch__slider {
  background: var(--switch-checked-bg);
}

.heatcfg-switch input:checked + .heatcfg-switch__slider .heatcfg-switch__checkmark {
  transform: scale(1);
}

.heatcfg-switch input:checked + .heatcfg-switch__slider .heatcfg-switch__cross {
  transform: scale(0);
}

.heatcfg-switch input:checked + .heatcfg-switch__slider::before {
  left: calc(100% - var(--effect-width) - (var(--effect-width) / 2) - var(--switch-offset));
}

.heatcfg-switch input:checked + .heatcfg-switch__slider .heatcfg-switch__circle {
  left: calc(100% - var(--circle-diameter) - var(--switch-offset));
  box-shadow: var(--circle-checked-shadow);
}

.heatcfg-switch input:disabled + .heatcfg-switch__slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.heatcfg-input :deep(.v-field) {
  border-radius: 12px;
  background: rgba(var(--v-theme-surface), 0.72);
}

.heatcfg-analytics-content {
  display: flex;
  flex-direction: column;
  min-height: 200px;
}

.gap-2 {
  gap: 8px;
}

.cursor-pointer {
  cursor: pointer;
}

@media (max-width: 960px) {
  .heatcfg-switch-grid,
  .heatcfg-form-grid {
    grid-template-columns: 1fr;
  }

  .heatcfg-form-item--full {
    grid-column: span 1;
  }
}

@media (max-width: 768px) {
  .heatcfg-page {
    padding: 14px;
  }

  .heatcfg-topbar {
    align-items: center;
    flex-wrap: nowrap;
  }

  .heatcfg-topbar__left {
    min-width: 0;
    flex: 1;
  }

  .heatcfg-topbar__meta {
    min-width: 0;
  }

  .heatcfg-topbar__right {
    justify-content: flex-end;
    flex-shrink: 0;
  }

  .heatcfg-switch-item,
  .heatcfg-switch-item__main {
    align-items: flex-start;
  }

  .heatcfg-switch-item {
    padding: 14px;
  }
}
</style>

