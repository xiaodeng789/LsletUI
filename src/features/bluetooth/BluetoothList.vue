<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import btIcon from '@/assets/bluetooth.png'
import { t } from '../../i18n'

const connectedDevices = ref([])
const btEnabled = ref(null)
const countdown = ref(30)

function getBatteryColor(value) {
  if (value > 60) return '#4ade80'
  if (value > 20) return '#facc15'
  return '#f87171'
}

function getStatusText() {
  if (btEnabled.value === false) return t('bt.off')
  if (btEnabled.value === true) return t('bt.on')
  return t('bt.detecting')
}

function getChipText() {
  if (btEnabled.value === false) return t('bt.off')
  return t('bt.scanning', { s: countdown.value })
}

function getChipColor() {
  if (btEnabled.value === false) return 'var(--error)'
  return 'var(--success)'
}

function getChipBg() {
  if (btEnabled.value === false) return 'rgba(255, 69, 58, 0.2)'
  return 'rgba(48, 209, 88, 0.2)'
}

function handleBluetoothDevicesUpdate(data) {
  console.log('[Bluetooth] 收到后端推送:', data)
  connectedDevices.value = data.devices || []
  btEnabled.value = data.btEnabled
}

function handleBluetoothCountdown(seconds) {
  countdown.value = seconds
}

function handleBluetoothStatus(enabled) {
  btEnabled.value = enabled
}

onMounted(() => {
  window.handleBluetoothDevicesUpdate = handleBluetoothDevicesUpdate
  window.handleBluetoothCountdown = handleBluetoothCountdown
  window.handleBluetoothStatus = handleBluetoothStatus
})

onBeforeUnmount(() => {
  if (window.handleBluetoothDevicesUpdate === handleBluetoothDevicesUpdate) {
    delete window.handleBluetoothDevicesUpdate
  }
  if (window.handleBluetoothCountdown === handleBluetoothCountdown) {
    delete window.handleBluetoothCountdown
  }
  if (window.handleBluetoothStatus === handleBluetoothStatus) {
    delete window.handleBluetoothStatus
  }
})
</script>

<template>
  <div class="bluetooth-container">
    <div class="bluetooth-header">
      <div class="header-left">
        <img :src="btIcon" class="bt-icon" alt="蓝牙" />
        <div>
          <h2 class="bluetooth-title">{{ t('bt.title') }}</h2>
          <div class="bluetooth-subtitle">{{ getStatusText() }}</div>
        </div>
      </div>
      <span class="status-chip" :style="{ color: getChipColor(), background: getChipBg() }">
        {{ getChipText() }}
      </span>
    </div>

    <div class="bluetooth-list">
      <template v-if="btEnabled !== false">
        <div
          v-for="device in connectedDevices"
          :key="device.id"
          class="bluetooth-item"
        >
        <div class="device-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z" fill="currentColor"/>
            <path d="M12 6c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z" fill="currentColor"/>
          </svg>
        </div>

        <div class="device-info">
          <div class="device-name">{{ device.name }}</div>
          <div class="device-battery">
            <div class="battery-bar">
              <div
                class="battery-fill"
                :style="{
                  width: device.batteryValue + '%',
                  backgroundColor: getBatteryColor(device.batteryValue)
                }"
              ></div>
            </div>
            <span class="battery-text">{{ device.battery }}</span>
          </div>
        </div>
      </div>
      </template>

      <div v-if="btEnabled === false" class="no-devices">
        {{ t('bt.offHint') }}
      </div>
      <div v-else-if="connectedDevices.length === 0" class="no-devices">
        {{ t('bt.noDevices') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.bluetooth-container {
  background: var(--card-bg);
  border-radius: var(--radius-card);
  padding: 12px;
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.bluetooth-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bt-icon {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.bluetooth-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.bluetooth-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.status-chip {
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.bluetooth-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bluetooth-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: var(--card-bg);
  border-radius: var(--radius-button);
  border: 1px solid var(--border-subtle);
  transition: all var(--duration-fast) var(--ease-out);
}

.bluetooth-item:hover {
  background: var(--card-bg-hover);
}

.device-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-bg);
  border-radius: 50%;
  color: var(--accent);
}

.device-info {
  flex: 1;
  min-width: 0;
}

.device-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.device-battery {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.battery-bar {
  flex: 1;
  height: 4px;
  background: var(--border-subtle);
  border-radius: 2px;
  overflow: hidden;
}

.battery-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.battery-text {
  font-size: 11px;
  color: var(--text-secondary);
  min-width: 30px;
  text-align: right;
}

.no-devices {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
