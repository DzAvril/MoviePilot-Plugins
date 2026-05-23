<template>
  <v-app>
    <v-main>
      <v-container>
        <v-row>
          <v-col cols="12">
            <h1>插件热度监控 - 本地开发</h1>
            <v-tabs v-model="tab">
              <v-tab value="page">详情页面</v-tab>
              <v-tab value="config">配置页面</v-tab>
              <v-tab value="dashboard">仪表板</v-tab>
            </v-tabs>
            
            <v-window v-model="tab">
              <v-window-item value="page">
                <Page :api="mockApi" />
              </v-window-item>
              <v-window-item value="config">
                <Config :api="mockApi" />
              </v-window-item>
              <v-window-item value="dashboard">
                <Dashboard :config="mockDashboardConfig" :api="mockApi" />
              </v-window-item>
            </v-window>
          </v-col>
        </v-row>
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import Page from './components/Page.vue'
import Config from './components/Config.vue'
import Dashboard from './components/Dashboard.vue'

const tab = ref('page')

// 生成测试用的日期数据
function generateMockDailyData(days = 30) {
  const data = {}
  const today = new Date()

  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(today)
    date.setDate(date.getDate() - i)
    const dateStr = date.toISOString().split('T')[0]

    // 生成随机下载量，模拟真实的增长趋势
    const baseValue = Math.max(0, Math.floor(Math.random() * 50) + (days - i) * 2)
    data[dateStr] = baseValue
  }

  return data
}

// Mock API for local development
const mockApi = {
  get: async (url) => {
    // 返回模拟数据
    if (url.includes('status')) {
      return {
        status: 'success',
        monitored_plugins: [
          {
            plugin_id: 'testplugin1',
            plugin_name: 'TestPlugin1',
            name: 'TestPlugin1',
            downloads: 1680,
            last_check: '2026-05-21 10:30:00',
            increment_since_last: 50,
            download_increment: 100,
            daily_downloads: generateMockDailyData(30)
          },
          {
            plugin_id: 'testplugin2',
            plugin_name: 'TestPlugin2',
            name: 'TestPlugin2',
            downloads: 2340,
            last_check: '2026-05-21 10:30:00',
            increment_since_last: 30,
            download_increment: 80,
            daily_downloads: generateMockDailyData(25)
          }
        ],
        total_downloads: 4020,
        total_daily_growth: 80,
        global_last_check_time: '2026-05-21 10:30:00',
        day_data: generateMockDailyData(30)
      }
    } else if (url.includes('plugin-list')) {
      // 插件列表 API
      return {
        status: 'success',
        plugins: [
          {
            id: 'testplugin1',
            name: 'TestPlugin1',
            icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png'
          },
          {
            id: 'testplugin2',
            name: 'TestPlugin2',
            icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png'
          },
          {
            id: 'testplugin3',
            name: 'TestPlugin3',
            icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png'
          }
        ]
      }
    } else if (url.includes('plugin-heatmap')) {
      // 插件热力图数据 API
      const pluginId = url.split('plugin_id=')[1] || 'testplugin1'
      const name = pluginId === 'testplugin1' ? 'TestPlugin1' : (pluginId === 'testplugin2' ? 'TestPlugin2' : 'TestPlugin3')

      return {
        status: 'success',
        plugin_id: pluginId,
        plugin_name: name,
        dayData: generateMockDailyData(60),
        current_downloads: Math.floor(Math.random() * 1000) + 1500
      }
    } else if (url.includes('config')) {
      // 获取配置 API
      return {
        status: 'success',
        config: {
          enabled: true,
          enable_notification: true,
          enable_mcp: true,
          cron: '0 8 * * *',
          download_increment: 100,
          monitored_plugins: ['testplugin1', 'testplugin2']
        }
      }
    } else if (url.includes('plugins')) {
      // 获取可用插件列表 API
      return {
        status: 'success',
        plugins: [
          { title: 'TestPlugin1 (下载量监控)', value: 'testplugin1', icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png' },
          { title: 'TestPlugin2 (通知测试)', value: 'testplugin2', icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png' },
          { title: 'TestPlugin3 (MCP助手)', value: 'testplugin3', icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png' }
        ]
      }
    } else if (url.includes('heatmap-data')) {
      // Dashboard 全局热力图 API
      return {
        status: 'success',
        yearData: { 2026: 4020 },
        monthData: { '2026-04': 1800, '2026-05': 2220 },
        dayData: generateMockDailyData(30)
      }
    } else if (url.includes('data')) {
      // Dashboard 汇总数据 API
      return {
        status: 'success',
        total_downloads: 4020,
        plugins: [
          {
            plugin_id: 'testplugin1',
            plugin_name: 'TestPlugin1',
            daily_downloads: generateMockDailyData(30)
          },
          {
            plugin_id: 'testplugin2',
            plugin_name: 'TestPlugin2',
            daily_downloads: generateMockDailyData(30)
          }
        ]
      }
    }

    return {}
  },
  post: async (url, data) => {
    if (url.includes('run_once')) {
      return { status: 'success', message: '已成功手动触发运行一次' }
    } else if (url.includes('reset-plugin-heatmap')) {
      return { status: 'success', message: '热力图历史数据重置成功' }
    } else if (url.includes('config')) {
      return { status: 'success', message: '配置保存成功' }
    }
    return { status: 'success' }
  }
}

// Mock dashboard config
const mockDashboardConfig = {
  cols: { cols: 12 },
  attrs: {
    refresh: 30,
    border: true,
    title: '插件热度监控',
    subtitle: '实时监控插件下载量增长趋势',
    icon: 'https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png'
  }
}
</script>
