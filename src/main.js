import { createApp } from 'vue'
import App from './App.vue'
import './styles/theme.css'

// 创建Vue应用
const app = createApp(App)

// 挂载应用
app.mount('#app')

// 入场动画控制（供 Python 后端调用）
// 注意：内容默认必须可见。首次显示时网页可能尚未加载完成，
// 后端的 playEntranceAnimation 调用会丢失；因此不能在加载时默认隐藏，
// 否则会永远停留在 opacity:0（黑幕）。
window.prepareEntranceAnimation = function() {
  document.documentElement.classList.add('panel-hidden')
  document.documentElement.classList.remove('panel-visible')
}

window.playEntranceAnimation = function() {
  requestAnimationFrame(() => {
    document.documentElement.classList.remove('panel-hidden')
    document.documentElement.classList.add('panel-visible')
  })
}

// 默认可见；仅当窗口已经处于隐藏状态（后端在页面加载前就调用过 prepare）
// 时才保持隐藏，等待后续 play。
if (!document.documentElement.classList.contains('panel-hidden')) {
  document.documentElement.classList.add('panel-visible')
}

// 开发环境提示
if (import.meta.env.DEV) {
  console.log('LsletUI 前端已启动（开发模式）')
}