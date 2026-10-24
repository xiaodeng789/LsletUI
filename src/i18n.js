import { ref } from 'vue'

// LsletUI 轻量国际化：zh / en 两套词典 + 响应式 t()
// 语言来源优先级：后端推送 settings > localStorage > 默认中文

const STORAGE_KEY = 'pyisland-lite-language'

export const locale = ref('zh')

function detectInitial() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'en' || saved === 'zh') return saved
  } catch (e) { /* 忽略 */ }
  return 'zh'
}

const messages = {
  zh: {
    // 设置面板
    'settings.title': '高级设置',
    'settings.general': '通用',
    'settings.autostart': '开机自启动',
    'settings.autostart.desc': '登录 Windows 后自动运行 LsletUI',
    'settings.autoDim': '自动减淡',
    'settings.autoDim.desc': '一段时间不操作后胶囊自动变暗',
    'settings.dimDelay': '无操作延迟',
    'settings.seconds': '{n} 秒',
    'settings.language': '语言',
    'settings.language.desc': '切换界面显示语言',
    'settings.alerts': '灵动岛提醒',
    'settings.notify.bluetooth': '蓝牙连接提醒',
    'settings.notify.bluetooth.desc': '耳机连接/断开时弹出通知',
    'settings.notify.download': '下载进度提醒',
    'settings.notify.download.desc': '浏览器/迅雷下载时显示进度',
    'settings.notify.hardware': '硬件高负载告警',
    'settings.notify.hardware.desc': 'CPU/内存/GPU 过载时提醒',
    // 关于页
    'about.memory': '内存优化',
    'about.memory.on': '已启用',
    'about.background': '后台运行',
    'about.background.running': '运行中',
    'about.help': '帮助',
    'about.advanced': '高级设置',
    'about.bug': 'Bug反馈',
    'about.bug.fail': '生成日志失败: {err}',
    'about.bug.saved': 'Bug日志已保存到:\n{path}',
    // 快捷链接
    'wait.title': '快捷链接',
    'wait.website': '官网',
    'wait.comingSoon': '还没开放',
    'wait.thanks': '感谢使用 LsletUI',
    // 蓝牙
    'bt.title': '蓝牙设备',
    'bt.off': '已关闭',
    'bt.on': '已开启',
    'bt.detecting': '检测中...',
    'bt.scanning': '扫描中 {s}s',
    'bt.offHint': '蓝牙已关闭，请在系统设置中开启蓝牙',
    'bt.noDevices': '未识别到设备',
    // 待办
    'todo.title': '待办事项',
    'todo.countActive': '{n} 项未完成',
    'todo.placeholder': '添加新的待办事项...',
    'todo.empty': '暂无待办事项',
    'todo.emptyActive': '没有进行中的待办',
    'todo.emptyDone': '还没有已完成的待办',
    'todo.filter_all': '全部',
    'todo.filter_active': '进行中',
    'todo.filter_done': '已完成',
    'todo.clearDone': '清空已完成',
    // 音乐
    'music.title': '正在播放',
    'music.subtitle': 'Windows SMTC 实时监控',
    'music.playing': '播放中',
    'music.notPlaying': '未播放',
    'music.unknownArtist': '未知歌手',
    'music.cover': '封面',
    'music.noMusic': '暂无正在播放的音乐',
    'music.noMusicHint': '打开网易云、QQ音乐等应用即可看到',
    'music.prev': '上一曲',
    'music.play': '播放',
    'music.pause': '暂停',
    'music.next': '下一曲',
    'music.footer': '基于 Windows SMTC，支持大部分音乐应用',
    // 格式转换
    'converter.title': '格式转换',
    'converter.count': '{n} 个',
    'converter.drop': '拖放文件到这里',
    'converter.dropHint': '点击选择文件，或从资源管理器直接拖入',
    'converter.convertAll': '全部转换',
    'converter.convert': '转换',
    'converter.converting': '转换中…',
    'converter.done': '已完成',
    'converter.failed': '失败',
    'converter.open': '打开',
    'converter.reveal': '在文件夹中显示',
    'converter.remove': '移出列表',
    'converter.noTarget': '该格式不支持转换',
    'converter.resultIn': '支持图片 / 音频 / 压缩包 / 文档，结果保存在源文件同目录',
  },
  en: {
    'settings.title': 'Advanced Settings',
    'settings.general': 'General',
    'settings.autostart': 'Launch at Startup',
    'settings.autostart.desc': 'Run LsletUI automatically after signing in to Windows',
    'settings.autoDim': 'Auto Dim',
    'settings.autoDim.desc': 'Dim the capsule automatically after inactivity',
    'settings.dimDelay': 'Inactivity Delay',
    'settings.seconds': '{n}s',
    'settings.language': 'Language',
    'settings.language.desc': 'Switch the interface language',
    'settings.alerts': 'Island Alerts',
    'settings.notify.bluetooth': 'Bluetooth Alerts',
    'settings.notify.bluetooth.desc': 'Notify when headphones connect or disconnect',
    'settings.notify.download': 'Download Progress',
    'settings.notify.download.desc': 'Show progress for browser and Thunder downloads',
    'settings.notify.hardware': 'Hardware Alerts',
    'settings.notify.hardware.desc': 'Alert when CPU / memory / GPU is overloaded',
    'about.memory': 'Memory Boost',
    'about.memory.on': 'Enabled',
    'about.background': 'Background',
    'about.background.running': 'Running',
    'about.help': 'Help',
    'about.advanced': 'Settings',
    'about.bug': 'Report Bug',
    'about.bug.fail': 'Failed to generate log: {err}',
    'about.bug.saved': 'Bug report saved to:\n{path}',
    'wait.title': 'Quick Links',
    'wait.website': 'Website',
    'wait.comingSoon': 'Coming soon',
    'wait.thanks': 'Thanks for using LsletUI',
    'bt.title': 'Bluetooth Devices',
    'bt.off': 'Off',
    'bt.on': 'On',
    'bt.detecting': 'Detecting...',
    'bt.scanning': 'Scanning {s}s',
    'bt.offHint': 'Bluetooth is off. Turn it on in system settings',
    'bt.noDevices': 'No devices found',
    'todo.title': 'To-dos',
    'todo.countActive': '{n} active',
    'todo.placeholder': 'Add a new to-do...',
    'todo.empty': 'Nothing to do yet',
    'todo.emptyActive': 'Nothing in progress',
    'todo.emptyDone': 'No completed to-dos yet',
    'todo.filter_all': 'All',
    'todo.filter_active': 'Active',
    'todo.filter_done': 'Done',
    'todo.clearDone': 'Clear done',
    'music.title': 'Now Playing',
    'music.subtitle': 'Live via Windows SMTC',
    'music.playing': 'Playing',
    'music.notPlaying': 'Idle',
    'music.unknownArtist': 'Unknown Artist',
    'music.cover': 'Cover',
    'music.noMusic': 'Nothing playing right now',
    'music.noMusicHint': 'Play something in NetEase Cloud Music, QQ Music, etc.',
    'music.prev': 'Previous',
    'music.play': 'Play',
    'music.pause': 'Pause',
    'music.next': 'Next',
    'music.footer': 'Powered by Windows SMTC, works with most music apps',
    'converter.title': 'Format Converter',
    'converter.count': '{n} files',
    'converter.drop': 'Drop files here',
    'converter.dropHint': 'Click to pick files, or drag from Explorer',
    'converter.convertAll': 'Convert all',
    'converter.convert': 'Convert',
    'converter.converting': 'Converting…',
    'converter.done': 'Done',
    'converter.failed': 'Failed',
    'converter.open': 'Open',
    'converter.reveal': 'Show in folder',
    'converter.remove': 'Remove',
    'converter.noTarget': 'Format not supported',
    'converter.resultIn': 'Images / audio / archives / docs — output is saved next to the source file',
  },
}

locale.value = detectInitial()

// 翻译：模板中调用 t(key, params)，locale 变化时自动重新渲染
export function t(key, params) {
  const dict = messages[locale.value] || messages.zh
  let text = dict[key] ?? messages.zh[key] ?? key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replaceAll(`{${k}}`, String(v))
    }
  }
  return text
}

export function setLocale(lang) {
  if (!messages[lang]) return
  locale.value = lang
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch (e) { /* 忽略 */ }
}

// 包装 window.handleSettingsUpdate：跟随设置推送切换语言，并转发给原有处理器
// 需在 App.vue onMounted 中调用（此时各子组件已注册自己的处理器）
export function installI18n() {
  const prev = window.handleSettingsUpdate
  window.handleSettingsUpdate = function (data) {
    if (data && typeof data === 'object' && data.language) {
      setLocale(data.language)
    }
    if (typeof prev === 'function') prev(data)
  }
}
