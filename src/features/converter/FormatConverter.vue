<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { t } from '../../i18n'

// 后端能力表（Pillow/ffmpeg/Office 检测结果），决定下拉可用性
const caps = ref({ image: false, audio: false, archive: true, word: false, excel: false, ppt: false })
// 转换条目：{uid, path, name, size, kind, target, status, outPath, error}
const items = ref([])
let _uidSeq = 0

// --- 格式矩阵（与后端 converter_backend.py 保持一致） ---
const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tiff', 'tif']
const AUDIO_EXTS = ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'aac', 'wma']
const DOC_MAP = {
  doc: 'word', docx: 'word', rtf: 'word',
  xls: 'excel', xlsx: 'excel',
  ppt: 'ppt', pptx: 'ppt',
}

function extOf(name) {
  return (name.split('.').pop() || '').toLowerCase()
}

function kindOf(name) {
  const ext = extOf(name)
  if (IMAGE_EXTS.includes(ext)) return 'image'
  if (AUDIO_EXTS.includes(ext)) return 'audio'
  if (ext === 'zip' || ext === 'tar' || ['gz', 'bz2', 'xz'].includes(ext)) return 'archive'
  if (DOC_MAP[ext]) return 'doc'
  return 'unsupported'
}

function targetsFor(item) {
  const ext = extOf(item.name)
  if (item.kind === 'image' && caps.value.image) {
    return ['png', 'jpg', 'webp', 'bmp', 'ico', 'tiff', 'gif']
      .filter(x => x !== ext && !(x === 'jpg' && ext === 'jpeg'))
  }
  if (item.kind === 'audio') {
    if (!caps.value.audio) return []
    return ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'aac'].filter(x => x !== ext)
  }
  if (item.kind === 'archive') {
    const all = ['zip', 'tar.gz', 'tar.bz2', 'tar.xz']
    if (ext === 'zip') return all.filter(x => x !== 'zip')
    if (ext === 'tar') return all.filter(x => x !== 'tar')
    return all.filter(x => x !== `tar.${ext}`)
  }
  if (item.kind === 'doc') {
    const app = DOC_MAP[ext]
    return caps.value[app] ? ['pdf'] : []
  }
  return []
}

// --- 后端推送回调 ---
function handleConvertCaps(c) {
  if (c && typeof c === 'object') caps.value = c
}

function handleConvertPicked(payload) {
  if (!Array.isArray(payload)) return
  for (const f of payload) {
    const item = {
      uid: `u${Date.now()}_${_uidSeq++}`,
      path: f.path,
      name: f.name || f.path.split(/[\\/]/).pop(),
      size: f.size || 0,
      kind: kindOf(f.name || f.path),
      target: '',
      status: 'idle', // idle | converting | done | error | unsupported
      outPath: '',
      error: '',
    }
    const opts = targetsFor(item)
    if (item.kind === 'unsupported') item.status = 'unsupported'
    else if (!opts.length) item.status = 'unsupported'
    else item.target = opts[0]
    // 同一文件不重复添加
    if (!items.value.some(it => it.path === item.path)) items.value.push(item)
  }
}

function handleConvertResult(result) {
  if (!result || result.id === undefined) return
  const item = items.value.find(it => it.uid === result.id)
  if (!item) return
  if (result.ok) {
    item.status = 'done'
    item.outPath = result.outPath || ''
    item.error = ''
  } else {
    item.status = 'error'
    item.error = result.error || 'error'
  }
}

// --- 用户操作 ---
function sendCommand(cmd) {
  // 项目统一的 console 命令通道（后端 javaScriptConsoleMessage 拦截）
  console.log('[PYISLAND_CMD]', cmd)
}

function pickFiles() { sendCommand('convert:pick') }

function startOne(item) {
  if (item.status === 'converting' || item.status === 'done') return
  if (item.status === 'unsupported' || !item.target) return
  sendCommand(`convert:start:${JSON.stringify([
    { id: item.uid, path: item.path, target: item.target }])}`)
}

function startAll() {
  const batch = items.value
    .filter(it => (it.status === 'idle' || it.status === 'error') && it.target)
    .map(it => ({ id: it.uid, path: it.path, target: it.target }))
  if (!batch.length) return
  sendCommand(`convert:start:${JSON.stringify(batch)}`)
  for (const it of items.value) {
    if (batch.some(b => b.id === it.uid)) it.status = 'converting'
  }
}

function removeItem(uid) {
  items.value = items.value.filter(it => it.uid !== uid)
}

function openOut(item) {
  if (item.outPath) sendCommand(`convert:open:${item.outPath}`)
}

function revealOut(item) {
  if (item.outPath) sendCommand(`convert:reveal:${item.outPath}`)
}

// --- 展示辅助 ---
const pendingCount = computed(() =>
  items.value.filter(it => it.status === 'idle' || it.status === 'error').length)

function formatSize(bytes) {
  if (!bytes) return ''
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function fileExt(name) {
  const ext = (name.split('.').pop() || '').toUpperCase()
  return ext.length <= 6 ? ext : ''
}

onMounted(() => {
  window.handleConvertCaps = handleConvertCaps
  window.handleConvertPicked = handleConvertPicked
  window.handleConvertResult = handleConvertResult
  // 页面加载完成后拉取一次能力表
  sendCommand('convert:caps')
})

onBeforeUnmount(() => {
  for (const key of ['handleConvertCaps', 'handleConvertPicked', 'handleConvertResult']) {
    delete window[key]
  }
})
</script>

<template>
  <div class="converter-container">
    <div class="converter-header">
      <div class="header-left">
        <h2 class="converter-title">{{ t('converter.title') }}</h2>
        <span v-if="items.length" class="file-count">
          {{ t('converter.count', { n: items.length }) }}
        </span>
      </div>
      <button
        v-if="pendingCount"
        class="convert-all-btn"
        @click="startAll"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        {{ t('converter.convertAll') }}
      </button>
    </div>

    <!-- 拖放/选择区域：点击弹原生文件对话框，从资源管理器拖入由 Qt 层拦截 -->
    <div class="drop-zone" @click="pickFiles">
      <div class="drop-icon-wrap">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
          <path d="M4 4h6l2 2h8a1 1 0 011 1v3H3V5a1 1 0 011-1z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
          <path d="M12 10v7m0 0l-3-3m3 3l3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <p class="drop-text">{{ t('converter.drop') }}</p>
      <p class="drop-hint">{{ t('converter.dropHint') }}</p>
    </div>

    <!-- 转换列表 -->
    <div v-if="items.length" class="file-list">
      <div v-for="item in items" :key="item.uid" class="file-item" :class="item.status">
        <div class="file-type-icon" :class="item.kind">
          <!-- 图片 -->
          <svg v-if="item.kind === 'image'" width="17" height="17" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.5"/><circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/><path d="M21 15l-5-5L5 21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <!-- 音频 -->
          <svg v-else-if="item.kind === 'audio'" width="17" height="17" viewBox="0 0 24 24" fill="none"><path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="1.5"/><circle cx="18" cy="16" r="3" stroke="currentColor" stroke-width="1.5"/></svg>
          <!-- 压缩包 -->
          <svg v-else-if="item.kind === 'archive'" width="17" height="17" viewBox="0 0 24 24" fill="none"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <!-- 文档 -->
          <svg v-else-if="item.kind === 'doc'" width="17" height="17" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M14 2v6h6M9 13h6M9 17h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          <!-- 不支持的格式 -->
          <svg v-else width="17" height="17" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>

        <div class="file-info">
          <div class="file-name" :title="item.name">{{ item.name }}</div>
          <div class="file-meta">
            <span v-if="formatSize(item.size)" class="file-size">{{ formatSize(item.size) }}</span>
            <span v-if="fileExt(item.name)" class="file-ext">{{ fileExt(item.name) }}</span>
            <span v-if="item.status === 'converting'" class="status-text converting-text">
              <span class="spinner"></span>{{ t('converter.converting') }}
            </span>
            <span v-else-if="item.status === 'done'" class="status-text done-text">✓ {{ t('converter.done') }}</span>
            <span v-else-if="item.status === 'error'" class="status-text error-text" :title="item.error">✗ {{ t('converter.failed') }}</span>
            <span v-else-if="item.status === 'unsupported'" class="status-text unsupported-text">{{ t('converter.noTarget') }}</span>
          </div>
        </div>

        <div class="item-controls">
          <!-- 目标格式下拉 -->
          <select
            v-if="item.status !== 'unsupported'"
            v-model="item.target"
            class="target-select"
            :disabled="item.status === 'converting' || item.status === 'done'"
          >
            <option v-for="opt in targetsFor(item)" :key="opt" :value="opt">
              {{ opt.toUpperCase() }}
            </option>
          </select>

          <!-- 单项转换按钮 -->
          <button
            v-if="item.status === 'idle' || item.status === 'error'"
            class="go-btn"
            :title="t('converter.convert')"
            @click="startOne(item)"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>

          <!-- 完成后：打开 / 定位 -->
          <template v-if="item.status === 'done'">
            <button class="action-btn" :title="t('converter.open')" @click="openOut(item)">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M14 4h6v6M20 4l-9 9M18 13v5a2 2 0 01-2 2H6a2 2 0 01-2-2V8a2 2 0 012-2h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button class="action-btn" :title="t('converter.reveal')" @click="revealOut(item)">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </template>

          <!-- 移出列表 -->
          <button class="action-btn danger" :title="t('converter.remove')" @click="removeItem(item.uid)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!items.length" class="empty-state">
      <span>{{ t('converter.resultIn') }}</span>
    </div>
  </div>
</template>

<style scoped>
.converter-container {
  background: var(--card-bg);
  border-radius: var(--radius-card);
  padding: 12px;
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.converter-header {
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

.converter-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.file-count {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--card-bg-hover);
  padding: 2px 8px;
  border-radius: 10px;
}

.convert-all-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--accent-bg);
  color: var(--accent);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-button);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.convert-all-btn:hover {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

/* 拖放/选择区域 */
.drop-zone {
  border: 2px dashed var(--border-subtle);
  border-radius: var(--radius-card);
  padding: 20px;
  text-align: center;
  transition: all 0.25s ease;
  cursor: pointer;
  margin-bottom: 12px;
}
.drop-zone:hover {
  border-color: var(--accent);
  background: var(--accent-bg);
}

.drop-icon-wrap {
  width: 44px;
  height: 44px;
  margin: 0 auto 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-bg);
  border-radius: 50%;
  color: var(--accent);
  transition: transform 0.25s;
}
.drop-zone:hover .drop-icon-wrap {
  transform: translateY(-2px);
}

.drop-text {
  font-size: 13px;
  font-weight: 500;
  margin: 0 0 4px;
  color: var(--text-primary);
}

.drop-hint {
  font-size: 11px;
  margin: 0;
  color: var(--text-tertiary);
}

/* 文件列表 */
.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 260px;
  overflow-y: auto;
}
.file-list::-webkit-scrollbar { width: 3px; }
.file-list::-webkit-scrollbar-track { background: transparent; }
.file-list::-webkit-scrollbar-thumb { background: var(--border-subtle); border-radius: 2px; }

.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--card-bg);
  border-radius: var(--radius-button);
  border: 1px solid var(--border-subtle);
  transition: all 0.2s;
}
.file-item:hover {
  background: var(--card-bg-hover);
}
.file-item.error {
  border-color: rgba(255, 69, 58, 0.35);
}
.file-item.unsupported {
  opacity: 0.55;
}

.file-type-icon {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  flex-shrink: 0;
}
.file-type-icon.image { background: rgba(59, 130, 246, 0.12); color: #3b82f6; }
.file-type-icon.audio { background: rgba(236, 72, 153, 0.12); color: #ec4899; }
.file-type-icon.archive { background: rgba(234, 179, 8, 0.12); color: #eab308; }
.file-type-icon.doc { background: rgba(34, 197, 94, 0.12); color: #22c55e; }
.file-type-icon.unsupported { background: var(--card-bg-hover); color: var(--text-secondary); }

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  min-height: 14px;
}

.file-size {
  font-size: 11px;
  color: var(--text-secondary);
}

.file-ext {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--card-bg-hover);
  padding: 1px 5px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

.status-text {
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.done-text { color: #22c55e; }
.error-text { color: var(--error); cursor: help; }
.unsupported-text { color: var(--text-tertiary); }

.converting-text {
  color: var(--accent);
}

.spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--accent-bg);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 右侧控件 */
.item-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.target-select {
  background: var(--card-bg-hover);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-size: 11px;
  padding: 3px 4px;
  cursor: pointer;
  outline: none;
  max-width: 76px;
}
.target-select:disabled {
  opacity: 0.6;
  cursor: default;
}
.target-select option {
  background: #1c1c20;
  color: #fff;
}

.go-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--accent-bg);
  color: var(--accent);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.go-btn:hover {
  background: var(--accent);
  color: #fff;
}

.action-btn {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  transition: all 0.2s;
}
.action-btn:hover {
  color: var(--accent);
  background: var(--accent-bg);
}
.action-btn.danger:hover {
  color: var(--error);
  background: rgba(255, 69, 58, 0.1);
}

.empty-state {
  text-align: center;
  padding: 8px 0 2px;
  color: var(--text-tertiary);
  font-size: 11px;
}
</style>
