<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import BluetoothList from './features/bluetooth/BluetoothList.vue'
import TodoPanel from './features/todo/TodoPanel.vue'
import FormatConverter from './features/converter/FormatConverter.vue'
import About from './features/about/about.vue'
import Wait from './features/wait/wait.vue'
import MusicPlayer from './features/music/MusicPlayer.vue'
import SettingsPanel from './features/settings/SettingsPanel.vue'
import { installI18n } from './i18n'

// 应用状态
const isReady = ref(false)
// ?view=settings 时为独立设置窗口模式，只渲染设置面板
const isSettingsView = ref(false)

onMounted(function () {
  const params = new URLSearchParams(window.location.search)
  isSettingsView.value = params.get('view') === 'settings'
  // 包装 window.handleSettingsUpdate，使界面语言跟随后端设置推送
  // （子组件 onMounted 先于父组件执行，此处包装不会覆盖它们的处理器）
  installI18n()
  setTimeout(() => {
    isReady.value = true
  }, 100)
})
</script>

<template>
  <div class="app-container">
    <div v-if="isSettingsView" class="panel-content">
      <SettingsPanel />
    </div>
    <div v-else class="panel-content">
      <BluetoothList />
      <MusicPlayer />
      <TodoPanel />
      <FormatConverter />
      <About />
      <Wait />
    </div>
  </div>
</template>

<style scoped>
.panel-content {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
