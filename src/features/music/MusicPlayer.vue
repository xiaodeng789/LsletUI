<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { t } from '../../i18n'

// SMTC 实时音乐信息
const smtcInfo = ref(null)
const hasMusic = computed(() => smtcInfo.value && smtcInfo.value.title)

// 处理后端推送的 SMTC 音乐信息
function handleSMTCMusicUpdate(info) {
  console.log('[MusicPlayer] 收到 SMTC 音乐信息:', info)
  smtcInfo.value = info
}

// 媒体控制图标（来自 backend/img 同款 SVG）
const icons = {
  prev: {
    vb: '2.60 2.60 4.80 4.80',
    d: 'M3.275 2.6a.6.6 0 0 0-.6.6v3.6a.6.6 0 0 0 1.2 0v-.205c0-.537 0-.806.078-.866a.2.2 0 0 1 .074-.036c.095-.024.315.15.755.499l.518.41c.622.492.933.739 1.193.75a.8.8 0 0 0 .679-.33c.153-.21.153-.607.153-1.4V4.378c0-.792 0-1.188-.153-1.399a.8.8 0 0 0-.679-.33c-.26.011-.571.258-1.193.75l-.518.41c-.44.348-.66.523-.756.499a.2.2 0 0 1-.073-.036c-.078-.06-.078-.329-.078-.866V3.2a.6.6 0 0 0-.6-.6',
  },
  next: {
    vb: '2.60 2.60 4.80 4.80',
    d: 'M6.725 2.6a.6.6 0 0 1 .6.6v3.6a.6.6 0 0 1-1.2 0v-.205c0-.537 0-.806-.078-.866a.2.2 0 0 0-.074-.036c-.095-.024-.315.15-.755.499l-.518.41c-.622.492-.933.739-1.193.75a.8.8 0 0 1-.679-.33c-.153-.21-.153-.607-.153-1.4V4.378c0-.792 0-1.188.153-1.399a.8.8 0 0 1 .679-.33c.26.011.571.258 1.193.75l.518.41c.44.348.66.523.756.499a.2.2 0 0 0 .073-.036c.078-.06.078-.329.078-.866V3.2a.6.6 0 0 1 .6-.6',
  },
  play: {
    vb: '2.90 2.43 5.14 5.14',
    d: 'M6.26 3.629c.795.592 1.192.889 1.23 1.287a1 1 0 0 1 0 .168c-.038.398-.435.695-1.23 1.287l-.485.361c-.762.568-1.144.852-1.463.839a.9.9 0 0 1-.66-.332c-.202-.248-.202-.723-.202-1.674v-1.13c0-.95 0-1.426.202-1.674a.9.9 0 0 1 .66-.332c.32-.013.7.271 1.463.839z',
  },
  pause: {
    vb: '2.30 2.30 5.40 5.40',
    d: 'M3.6 2.3a.7.7 0 0 1 .7.7v4a.7.7 0 0 1-1.4 0V3a.7.7 0 0 1 .7-.7m2.8 0a.7.7 0 0 1 .7.7v4a.7.7 0 1 1-1.4 0V3a.7.7 0 0 1 .7-.7',
  },
}
const toggleIcon = computed(() => (smtcInfo.value && smtcInfo.value.playing ? icons.pause : icons.play))

// 发送媒体控制命令到后端
function sendMediaCommand(command) {
  console.log('[PYISLAND_CMD]', command)
}

// 专辑封面 URL（base64）
const albumArtUrl = computed(() => {
  if (smtcInfo.value && smtcInfo.value.thumbnail) {
    return `data:image/jpeg;base64,${smtcInfo.value.thumbnail}`
  }
  return null
})

onMounted(() => {
  window.handleSMTCMusicUpdate = handleSMTCMusicUpdate
})

onBeforeUnmount(() => {
  if (window.handleSMTCMusicUpdate === handleSMTCMusicUpdate) {
    delete window.handleSMTCMusicUpdate
  }
})
</script>

<template>
  <div class="music-container">
    <div class="music-header">
      <div>
        <h2 class="music-title">{{ t('music.title') }}</h2>
        <div class="music-subtitle">{{ t('music.subtitle') }}</div>
      </div>
      <span class="status-chip" :class="{ active: hasMusic && smtcInfo.playing }">
        {{ hasMusic && smtcInfo.playing ? t('music.playing') : t('music.notPlaying') }}
      </span>
    </div>

    <!-- 有音乐时显示 -->
    <div v-if="hasMusic" class="now-playing">
      <div class="album-art">
        <img v-if="albumArtUrl" :src="albumArtUrl" :alt="t('music.cover')" />
        <div v-else class="album-art-placeholder">♪</div>
      </div>
      <div class="track-info">
        <div class="track-title">{{ smtcInfo.title }}</div>
        <div class="track-artist">{{ smtcInfo.artist || t('music.unknownArtist') }}</div>
        <div class="track-album" v-if="smtcInfo.album">{{ smtcInfo.album }}</div>
      </div>
    </div>

    <!-- 无音乐时显示 -->
    <div v-else class="no-music">
      <div class="no-music-icon">🎵</div>
      <div class="no-music-text">{{ t('music.noMusic') }}</div>
      <div class="no-music-hint">{{ t('music.noMusicHint') }}</div>
    </div>

    <!-- 控制按钮 -->
    <div v-if="hasMusic" class="controls">
      <button class="control-btn" @click="sendMediaCommand('prev')" :title="t('music.prev')">
        <svg class="ctrl-icon" :viewBox="icons.prev.vb">
          <path :d="icons.prev.d" />
        </svg>
      </button>
      <button class="control-btn play-btn" @click="sendMediaCommand('playpause')" :title="smtcInfo.playing ? t('music.pause') : t('music.play')">
        <svg class="ctrl-icon" :viewBox="toggleIcon.vb">
          <path :d="toggleIcon.d" />
        </svg>
      </button>
      <button class="control-btn" @click="sendMediaCommand('next')" :title="t('music.next')">
        <svg class="ctrl-icon" :viewBox="icons.next.vb">
          <path :d="icons.next.d" />
        </svg>
      </button>
    </div>

    <div class="music-footer">
      <div class="footer-text">{{ t('music.footer') }}</div>
    </div>
  </div>
</template>

<style scoped>
.music-container {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}

.music-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  gap: 12px;
}

.music-title {
  color: white;
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0 0 4px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.music-subtitle {
  color: rgba(255, 255, 255, 0.65);
  font-size: 0.82rem;
  text-align: left;
}

.status-chip {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
  font-weight: 400;
  background: rgba(255, 255, 255, 0.1);
  padding: 4px 12px;
  border-radius: 12px;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.status-chip.active {
  background: rgba(34, 197, 94, 0.3);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.now-playing {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 8px 0;
}

.album-art {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.album-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.album-art-placeholder {
  font-size: 1.8rem;
  color: rgba(255, 255, 255, 0.5);
}

.track-info {
  flex: 1;
  min-width: 0;
}

.track-title {
  color: white;
  font-size: 0.98rem;
  font-weight: 600;
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-artist {
  color: rgba(255, 255, 255, 0.75);
  font-size: 0.85rem;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-album {
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.78rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.no-music {
  text-align: center;
  padding: 24px 0;
}

.no-music-icon {
  font-size: 2.5rem;
  margin-bottom: 8px;
  opacity: 0.6;
}

.no-music-text {
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.95rem;
  margin-bottom: 4px;
}

.no-music-hint {
  color: rgba(255, 255, 255, 0.45);
  font-size: 0.78rem;
}

.controls {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.control-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.08);
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ctrl-icon {
  width: 18px;
  height: 18px;
  fill: currentColor;
}

.play-btn .ctrl-icon {
  width: 22px;
  height: 22px;
}

.control-btn:hover {
  background: rgba(255, 255, 255, 0.18);
  transform: scale(1.05);
}

.control-btn:active {
  transform: scale(0.95);
}

.play-btn {
  width: 48px;
  height: 48px;
  font-size: 1.3rem;
  background: rgba(255, 255, 255, 0.12);
}

.music-footer {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.footer-text {
  color: rgba(255, 255, 255, 0.4);
  font-size: 0.75rem;
  text-align: center;
}
</style>
