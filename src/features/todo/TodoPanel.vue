<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { t } from '../../i18n'

const todos = ref([])
const newTodo = ref('')
const storageKey = 'pyisland-lite-todos'

// 筛选：all / active / done
const filter = ref('all')
// 双击编辑态
const editingId = ref(null)
const editText = ref('')
const _editInput = ref(null)

function loadTodos() {
  try {
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed)) todos.value = parsed
    }
  } catch (e) {
    console.error('[Todo] 加载待办事项失败:', e)
  }
}

function saveTodos() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(todos.value))
  } catch (e) {
    console.error('[Todo] 保存待办事项失败:', e)
  }
}

function addTodo() {
  const text = newTodo.value.trim()
  if (!text) return
  todos.value.push({
    id: Date.now(),
    text,
    completed: false,
    createdAt: new Date().toISOString(),
  })
  newTodo.value = ''
}

function toggleTodo(id) {
  const todo = todos.value.find(x => x.id === id)
  if (todo) todo.completed = !todo.completed
}

function deleteTodo(id) {
  todos.value = todos.value.filter(x => x.id !== id)
  if (editingId.value === id) cancelEdit()
}

// --- 编辑（双击进入，Enter/失焦保存，Esc 取消） ---
function startEdit(todo) {
  editingId.value = todo.id
  editText.value = todo.text
  nextTick(() => _editInput.value && _editInput.value.focus())
}

function commitEdit() {
  if (editingId.value === null) return
  const text = editText.value.trim()
  const todo = todos.value.find(x => x.id === editingId.value)
  if (todo) {
    if (text) todo.text = text
    // 清空编辑视为取消，不删条目
  }
  editingId.value = null
  editText.value = ''
}

function cancelEdit() {
  editingId.value = null
  editText.value = ''
}

// --- 筛选与统计 ---
const activeCount = computed(() => todos.value.filter(x => !x.completed).length)
const doneCount = computed(() => todos.value.length - activeCount.value)
const hasDone = computed(() => doneCount.value > 0)

const visibleTodos = computed(() => {
  if (filter.value === 'active') return todos.value.filter(x => !x.completed)
  if (filter.value === 'done') return todos.value.filter(x => x.completed)
  return todos.value
})

const isEmptyFiltered = computed(() =>
  todos.value.length > 0 && visibleTodos.value.length === 0)

function clearDone() {
  todos.value = todos.value.filter(x => !x.completed)
}

// 统一由 watch 持久化（避免多处手动保存重复写盘）
watch(todos, saveTodos, { deep: true })

function setFilter(f) {
  filter.value = f
}

function emptyText() {
  if (todos.value.length === 0) return t('todo.empty')
  if (filter.value === 'active') return t('todo.emptyActive')
  return t('todo.emptyDone')
}

onMounted(loadTodos)
</script>

<template>
  <div class="todo-container">
    <div class="todo-header">
      <h2 class="todo-title">{{ t('todo.title') }}</h2>
      <span class="todo-count" :class="{ 'all-done': todos.length > 0 && activeCount === 0 }">
        {{ t('todo.countActive', { n: activeCount }) }}
      </span>
    </div>

    <!-- 添加待办事项 -->
    <div class="todo-input-container">
      <input
        v-model="newTodo"
        @keyup.enter="addTodo"
        class="todo-input"
        :placeholder="t('todo.placeholder')"
        type="text"
      />
      <button @click="addTodo" class="add-button">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 4V20M4 12H20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </button>
    </div>

    <!-- 筛选 -->
    <div class="todo-toolbar">
      <div class="filter-group">
        <button
          v-for="f in ['all', 'active', 'done']"
          :key="f"
          class="filter-btn"
          :class="{ active: filter === f }"
          @click="setFilter(f)"
        >
          {{ t(`todo.filter_${f}`) }}
        </button>
      </div>
      <button v-if="hasDone" class="clear-done-btn" @click="clearDone">
        {{ t('todo.clearDone') }}
      </button>
    </div>

    <!-- 待办事项列表 -->
    <div class="todo-list">
      <div
        v-for="todo in visibleTodos"
        :key="todo.id"
        class="todo-item"
        :class="{ completed: todo.completed, editing: editingId === todo.id }"
        @dblclick="startEdit(todo)"
      >
        <button
          @click="toggleTodo(todo.id)"
          class="todo-checkbox"
          :class="{ checked: todo.completed }"
        >
          <svg v-if="todo.completed" width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M20 6L9 17L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <input
          v-if="editingId === todo.id"
          ref="_editInput"
          v-model="editText"
          class="todo-edit-input"
          :placeholder="t('todo.placeholder')"
          @keyup.enter="commitEdit"
          @keyup.esc="cancelEdit"
          @blur="commitEdit"
        />
        <span v-else class="todo-text" :title="todo.text">{{ todo.text }}</span>

        <button @click.stop="deleteTodo(todo.id)" class="delete-button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <div v-if="isEmptyFiltered || todos.length === 0" class="no-todos">
        {{ emptyText() }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.todo-container {
  background: var(--card-bg);
  border-radius: var(--radius-card);
  padding: 12px;
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.todo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.todo-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.todo-count {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--card-bg-hover);
  padding: 2px 8px;
  border-radius: 10px;
}

.todo-count.all-done {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.todo-input-container {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.todo-input {
  flex: 1;
  background: var(--card-bg);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-button);
  padding: 8px 12px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out);
}

.todo-input:focus {
  border-color: var(--border-focus);
}

.todo-input::placeholder {
  color: var(--text-tertiary);
}

.add-button {
  background: var(--accent-bg);
  border: 1px solid var(--accent);
  border-radius: var(--radius-button);
  color: var(--accent);
  width: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.add-button:hover {
  background: var(--accent-bg-hover);
}

/* 筛选工具条 */
.todo-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  min-height: 22px;
}

.filter-group {
  display: flex;
  gap: 2px;
  background: var(--card-bg-hover);
  border-radius: 8px;
  padding: 2px;
}

.filter-btn {
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.filter-btn.active {
  background: var(--accent);
  color: #fff;
}

.clear-done-btn {
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.clear-done-btn:hover {
  color: var(--error);
  background: rgba(255, 69, 58, 0.1);
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.todo-list::-webkit-scrollbar {
  width: 3px;
}
.todo-list::-webkit-scrollbar-track {
  background: transparent;
}
.todo-list::-webkit-scrollbar-thumb {
  background: var(--border-subtle);
  border-radius: 2px;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: var(--card-bg);
  border-radius: var(--radius-button);
  border: 1px solid var(--border-subtle);
  transition: all var(--duration-fast) var(--ease-out);
}

.todo-item:hover {
  background: var(--card-bg-hover);
}

.todo-item.completed {
  opacity: 0.6;
}

.todo-item.editing {
  border-color: var(--border-focus);
}

.todo-checkbox {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  color: transparent;
  flex-shrink: 0;
}

.todo-checkbox.checked {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.todo-text {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: text;
}

.todo-item.completed .todo-text {
  text-decoration: line-through;
  color: var(--text-tertiary);
}

.todo-edit-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  padding: 0;
}

.delete-button {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  opacity: 0;
  transition: all var(--duration-fast) var(--ease-out);
  flex-shrink: 0;
}

.todo-item:hover .delete-button {
  opacity: 1;
}

.delete-button:hover {
  color: var(--error);
  background: rgba(255, 69, 58, 0.1);
}

.no-todos {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
