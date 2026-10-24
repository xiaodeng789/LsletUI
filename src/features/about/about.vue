<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { t } from '../../i18n'

// 应用信息
const appName = ref('LsletUI')
const version = ref('0.1.0')
const currentTime = ref('')

// 更新当前时间
function updateTime() {
  const now = new Date()
  const hours = now.getHours().toString().padStart(2, '0')
  const minutes = now.getMinutes().toString().padStart(2, '0')
  const seconds = now.getSeconds().toString().padStart(2, '0')
  currentTime.value = `${hours}:${minutes}:${seconds}`
}

// 打开高级设置独立窗口
function openSettings() {
  console.log('[PYISLAND_CMD] open:settings')
}

// 打开帮助网站
function openHelp() {
  console.log('[PYISLAND_CMD] open:url:https://lsletui.xiaodeng123.cn')
}

// 生成Bug反馈日志
function reportBug() {
  console.log('[PYISLAND_CMD] bug:report')
}

// 处理Bug报告结果
function handleBugReportResult(filePath, error) {
  if (error) {
    alert(t('about.bug.fail', { err: error }))
  } else if (filePath) {
    alert(t('about.bug.saved', { path: filePath }))
  }
}

// 时间更新定时器
let timeInterval = null

onMounted(() => {
  // 注册全局函数
  window.handleBugReportResult = handleBugReportResult
  
  // 启动时间更新
  updateTime()
  timeInterval = setInterval(updateTime, 1000)
})

onBeforeUnmount(() => {
  // 清理定时器
  if (timeInterval) {
    clearInterval(timeInterval)
  }
  
  // 清理全局函数
  if (window.handleBugReportResult === handleBugReportResult) {
    delete window.handleBugReportResult
  }
})
</script>

<template>
  <div class="about-container">
    <div class="about-header">
      <div class="logo-section">
        <div class="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="app-info">
          <h1 class="app-name">{{ appName }}</h1>
          <div class="app-version">v{{ version }}</div>
        </div>
      </div>
      
      <div class="time-display">
        <div class="current-time">{{ currentTime }}</div>
      </div>
    </div>
    
    <!-- 状态信息 -->
    <div class="status-section">
      <div class="status-item">
        <span class="status-label">{{ t('about.memory') }}</span>
        <span class="status-value optimized">{{ t('about.memory.on') }}</span>
      </div>

      <div class="status-item">
        <span class="status-label">{{ t('about.background') }}</span>
        <span class="status-value active">{{ t('about.background.running') }}</span>
      </div>
    </div>
    
    <!-- 快捷操作 -->
    <div class="quick-actions">
      <button class="action-button" @click="openHelp">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 15V17M12 7V13M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <span>{{ t('about.help') }}</span>
      </button>
      
      <button class="action-button" @click="openSettings">
        <svg width="16" height="16" viewBox="1.98 1.98 6.04 6.04" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
          <path d="M4.453 2.445c.099-.623.995-.623 1.094 0a.554.554 0 0 0 .872.361c.51-.37 1.145.264.775.774a.554.554 0 0 0 .361.872c.623.1.623.996 0 1.095a.554.554 0 0 0-.361.873c.37.51-.264 1.144-.775.774a.554.554 0 0 0-.872.361c-.099.623-.995.623-1.094 0a.554.554 0 0 0-.872-.361c-.51.37-1.145-.264-.775-.774a.554.554 0 0 0-.361-.873c-.623-.099-.623-.996 0-1.095a.554.554 0 0 0 .361-.872c-.37-.51.264-1.144.775-.774a.554.554 0 0 0 .872-.361M5 3.8a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4"/>
        </svg>
        <span>{{ t('about.advanced') }}</span>
      </button>

      <button class="action-button bug-button" @click="reportBug">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="currentColor"/>
        </svg>
        <span>{{ t('about.bug') }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.about-container {
  background: var(--card-bg);
  border-radius: var(--radius-card);
  padding: 12px;
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.about-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.logo-section {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--accent), #0077ed);
  border-radius: var(--radius-button);
  color: white;
}

.app-info {
  display: flex;
  flex-direction: column;
}

.app-name {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
}

.app-version {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.time-display {
  text-align: right;
}

.current-time {
  font-size: 24px;
  font-weight: 300;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: 2px;
}

.status-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--card-bg);
  border-radius: var(--radius-button);
  border: 1px solid var(--border-subtle);
}

.status-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.status-value {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
}

.status-value.optimized {
  background: var(--accent-bg);
  color: var(--accent);
}

.status-value.active {
  background: rgba(255, 214, 10, 0.2);
  color: var(--warning);
}

.quick-actions {
  display: flex;
  gap: 8px;
}

.action-button {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  background: var(--card-bg);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-button);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.action-button:hover {
  background: var(--card-bg-hover);
  color: var(--text-primary);
}

.action-button span {
  font-size: 11px;
}

.action-button.bug-button {
  color: var(--error);
}

.action-button.bug-button:hover {
  background: rgba(255, 69, 58, 0.1);
  color: var(--error);
}
</style>