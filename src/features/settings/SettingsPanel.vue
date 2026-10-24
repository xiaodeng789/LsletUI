<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { t, setLocale } from '../../i18n'

// 设置状态（以后端推送为准，本地先做乐观更新）
const settings = ref({
  autostart: false,
  auto_dim: true,
  auto_dim_delay: 10000,
  notify_bluetooth: true,
  notify_download: true,
  notify_hardware: true,
  language: 'zh',
})

const delayOptions = [5000, 10000, 30000]

// 语言选项（固定用各自母语显示）
const languageOptions = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
]

// 通知开关配置（key/标签/描述，文案走 i18n）
const notifyOptions = [
  { key: 'notify_bluetooth', labelKey: 'settings.notify.bluetooth', descKey: 'settings.notify.bluetooth.desc' },
  { key: 'notify_download', labelKey: 'settings.notify.download', descKey: 'settings.notify.download.desc' },
  { key: 'notify_hardware', labelKey: 'settings.notify.hardware', descKey: 'settings.notify.hardware.desc' },
]

// 接收后端设置推送
function handleSettingsUpdate(data) {
  if (data && typeof data === 'object') {
    settings.value = { ...settings.value, ...data }
  }
}

// 向后端发送设置命令
function sendCommand(cmd) {
  console.log('[PYISLAND_CMD]', cmd)
}

function toggleAutostart() {
  const next = !settings.value.autostart
  settings.value.autostart = next
  sendCommand(`settings:set:autostart:${next}`)
}

function toggleAutoDim() {
  const next = !settings.value.auto_dim
  settings.value.auto_dim = next
  sendCommand(`settings:set:auto_dim:${next}`)
}

function chooseDelay(value) {
  if (settings.value.auto_dim_delay === value) return
  settings.value.auto_dim_delay = value
  sendCommand(`settings:set:auto_dim_delay:${value}`)
}

function chooseLanguage(value) {
  if (settings.value.language === value) return
  settings.value.language = value
  setLocale(value)
  sendCommand(`settings:set:language:${value}`)
}

function toggleNotify(key) {
  const next = !settings.value[key]
  settings.value[key] = next
  sendCommand(`settings:set:${key}:${next}`)
}

onMounted(() => {
  window.handleSettingsUpdate = handleSettingsUpdate
  // 面板加载完成后主动拉取一次（后端也会补推，双保险）
  sendCommand('settings:get')
})

onBeforeUnmount(() => {
  if (window.handleSettingsUpdate === handleSettingsUpdate) {
    delete window.handleSettingsUpdate
  }
})
</script>

<template>
  <div class="settings-container" id="settings-card">
    <div class="settings-title">{{ t('settings.title') }}</div>

    <!-- 通用 -->
    <div class="group-head">{{ t('settings.general') }}</div>

    <!-- 开机自启动 -->
    <div class="setting-row">
      <div class="setting-info">
        <div class="setting-label">{{ t('settings.autostart') }}</div>
        <div class="setting-desc">{{ t('settings.autostart.desc') }}</div>
      </div>
      <button
        class="switch"
        :class="{ on: settings.autostart }"
        role="switch"
        :aria-checked="settings.autostart"
        @click="toggleAutostart"
      >
        <span class="switch-knob"></span>
      </button>
    </div>

    <!-- 自动减淡 -->
    <div class="setting-row">
      <div class="setting-info">
        <div class="setting-label">{{ t('settings.autoDim') }}</div>
        <div class="setting-desc">{{ t('settings.autoDim.desc') }}</div>
      </div>
      <button
        class="switch"
        :class="{ on: settings.auto_dim }"
        role="switch"
        :aria-checked="settings.auto_dim"
        @click="toggleAutoDim"
      >
        <span class="switch-knob"></span>
      </button>
    </div>

    <!-- 减淡延迟选择 -->
    <transition name="expand">
      <div v-if="settings.auto_dim" class="delay-block">
        <div class="delay-label">{{ t('settings.dimDelay') }}</div>
        <div class="segmented">
          <button
            v-for="value in delayOptions"
            :key="value"
            class="segment"
            :class="{ active: settings.auto_dim_delay === value }"
            @click="chooseDelay(value)"
          >
            {{ t('settings.seconds', { n: value / 1000 }) }}
          </button>
        </div>
      </div>
    </transition>

    <!-- 语言 -->
    <div class="delay-block">
      <div class="delay-label">{{ t('settings.language') }}</div>
      <div class="segmented">
        <button
          v-for="opt in languageOptions"
          :key="opt.value"
          class="segment"
          :class="{ active: settings.language === opt.value }"
          @click="chooseLanguage(opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
      <div class="delay-label lang-desc">{{ t('settings.language.desc') }}</div>
    </div>

    <!-- 灵动岛提醒 -->
    <div class="group-head">{{ t('settings.alerts') }}</div>
    <div
      v-for="opt in notifyOptions"
      :key="opt.key"
      class="setting-row"
    >
      <div class="setting-info">
        <div class="setting-label">{{ t(opt.labelKey) }}</div>
        <div class="setting-desc">{{ t(opt.descKey) }}</div>
      </div>
      <button
        class="switch"
        :class="{ on: settings[opt.key] }"
        role="switch"
        :aria-checked="settings[opt.key]"
        @click="toggleNotify(opt.key)"
      >
        <span class="switch-knob"></span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.settings-container {
  background: var(--card-bg);
  border-radius: var(--radius-card);
  padding: 12px;
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.settings-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.group-head {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 12px 2px 6px;
}

.group-head:first-of-type {
  margin-top: 0;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 2px;
  gap: 12px;
}

.setting-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.setting-label {
  font-size: 13px;
  color: var(--text-primary);
}

.setting-desc {
  font-size: 11px;
  color: var(--text-secondary);
}

/* iOS 风格开关 */
.switch {
  flex-shrink: 0;
  width: 44px;
  height: 26px;
  border-radius: 13px;
  border: none;
  background: rgba(120, 120, 128, 0.32);
  position: relative;
  cursor: pointer;
  transition: background-color 0.2s ease;
  padding: 0;
}

.switch.on {
  background: var(--success, #30d158);
}

.switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.25);
  transition: transform 0.2s ease;
}

.switch.on .switch-knob {
  transform: translateX(18px);
}

/* 延迟分段选择 */
.delay-block {
  padding: 10px 2px 4px;
  border-top: 1px solid var(--border-subtle);
}

.delay-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.lang-desc {
  margin-top: 8px;
  margin-bottom: 0;
}

.segmented {
  display: flex;
  background: rgba(120, 120, 128, 0.16);
  border-radius: 9px;
  padding: 2px;
  gap: 2px;
}

.segment {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 6px 0;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.segment.active {
  background: var(--accent, #0a84ff);
  color: #fff;
  font-weight: 600;
}

.segment:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 展开/收起动画 */
.expand-enter-active,
.expand-leave-active {
  transition: opacity 0.2s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
}
</style>
