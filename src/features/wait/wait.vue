<script setup>
import { t } from '../../i18n'

// 链接列表（其余快捷链接尚未开放）
const links = [
  {
    nameKey: 'wait.website',
    url: 'https://pyisland.com',
    icon: 'globe',
    available: false
  },
  {
    name: 'GitHub',
    url: 'https://github.com/pyisland',
    icon: 'code',
    available: false
  }
]

// 点击链接
function openLink(link) {
  // 尚未开放的链接不响应
  if (!link.available) {
    return
  }
  // 通过Python后端打开链接
  if (window.pywebview) {
    window.pywebview.api.open_url(link.url)
  } else {
    window.open(link.url, '_blank')
  }
}

// 获取图标SVG
function getIconSvg(icon) {
  const icons = {
    globe: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="currentColor" stroke-width="2"/>
      <path d="M2 12H22" stroke="currentColor" stroke-width="2"/>
      <path d="M12 2C14.5013 4.73835 15.9228 8.29203 16 12C15.9228 15.708 14.5013 19.2616 12 22C9.49872 19.2616 8.07725 15.708 8 12C8.07725 8.29203 9.49872 4.73835 12 2Z" stroke="currentColor" stroke-width="2"/>
    </svg>`,
    code: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 18L22 12L16 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M8 6L2 12L8 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`
  }
  return icons[icon] || icons.globe
}
</script>

<template>
  <div class="wait-container">
    <div class="wait-header">
      <h2 class="wait-title">{{ t('wait.title') }}</h2>
    </div>

    <div class="links-grid">
      <button
        v-for="link in links"
        :key="link.url"
        class="link-button"
        :class="{ 'link-disabled': !link.available }"
        @click="openLink(link)"
      >
        <div class="link-icon" v-html="getIconSvg(link.icon)"></div>
        <span class="link-name">{{ link.nameKey ? t(link.nameKey) : link.name }}</span>
        <span class="link-status" v-if="!link.available">{{ t('wait.comingSoon') }}</span>
      </button>
    </div>

    <div class="footer-info">
      <p class="copyright">LsletUI</p>
      <p class="thanks">{{ t('wait.thanks') }}</p>
    </div>
  </div>
</template>

<style scoped>
.wait-container {
  background: var(--card-bg);
  border-radius: var(--radius-card);
  padding: 12px;
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.wait-header {
  margin-bottom: 12px;
}

.wait-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.links-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.link-button {
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

.link-button:hover {
  background: var(--card-bg-hover);
  color: var(--text-primary);
  transform: translateY(-2px);
}

.link-button.link-disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.link-button.link-disabled:hover {
  background: var(--card-bg);
  color: var(--text-secondary);
  transform: none;
}

.link-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-bg);
  border-radius: var(--radius-button);
  color: var(--accent);
}

.link-name {
  font-size: 12px;
  font-weight: 500;
}

.link-status {
  font-size: 10px;
  color: var(--text-tertiary);
}

.footer-info {
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

.copyright {
  font-size: 11px;
  color: var(--text-tertiary);
  margin: 0 0 4px;
}

.thanks {
  font-size: 10px;
  color: var(--text-tertiary);
  margin: 0;
}
</style>