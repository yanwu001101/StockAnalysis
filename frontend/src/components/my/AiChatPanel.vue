<template>
  <div class="ai-chat" :class="{ mobile: isMobile }">
    <!-- 会话栏 -->
    <div class="chat-top">
      <el-select
        v-model="sessionId"
        placeholder="新对话"
        size="small"
        class="session-select"
        @change="loadMessages"
      >
        <el-option v-for="s in sessions" :key="s.id" :label="s.title" :value="s.id" />
      </el-select>
      <el-button size="small" @click="newSession">新对话</el-button>
      <el-button
        v-if="sessionId"
        size="small"
        type="danger"
        plain
        :disabled="deleting"
        @click="removeSession"
      >删除</el-button>
    </div>

    <!-- 消息流 -->
    <div ref="listRef" class="chat-list">
      <EmptyState
        v-if="!messages.length && !pending"
        title="和你的 AI 金融顾问聊聊"
        description="可以问行情看法、持仓思路、风险控制、资产配置等。AI 只做分析参考，不构成投资建议；首次使用请先在「持仓助手」里配置模型。"
      />
      <template v-for="(m, i) in messages" :key="i">
        <div class="bubble-row" :class="m.role">
          <div class="bubble" v-html="renderContent(m.content)" />
        </div>
      </template>
      <div v-if="pending" class="bubble-row assistant">
        <div class="bubble typing"><span /><span /><span /></div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input">
      <el-input
        v-model="draft"
        type="textarea"
        :autosize="{ minRows: isMobile ? 2 : 3, maxRows: 6 }"
        :placeholder="listening ? '正在听你说…' : '输入你的问题，Enter 发送，Shift+Enter 换行'"
        @keydown="onKeydown"
      />
      <div class="input-actions">
        <button
          v-if="voiceSupported"
          type="button"
          class="mic-btn"
          :class="{ listening }"
          :title="listening ? '停止录音' : '语音输入'"
          @click="toggleVoice"
        >{{ listening ? '●' : '🎤' }}</button>
        <span v-if="listening" class="listening-tip">正在聆听，请说话…</span>
        <span class="disclaimer">仅供参考，不构成投资建议 · 勿透露密码</span>
        <el-button type="primary" size="small" :loading="pending" :disabled="!draft.trim()" @click="send">
          {{ pending ? '思考中…' : '发送' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDevice } from '@/composables/useDevice'
import {
  chatAi, getChatSessions, getChatMessages, deleteChatSession,
  type ChatMessageItem, type ChatSessionItem,
} from '@/api/ai'

const { isMobile } = useDevice()

const sessionId = ref<number | null>(null)
const sessions = ref<ChatSessionItem[]>([])
const messages = ref<ChatMessageItem[]>([])
const draft = ref('')
const pending = ref(false)
const deleting = ref(false)
const listRef = ref<HTMLElement | null>(null)

// ---- 会话 ----
async function loadSessions(keepId = true) {
  try {
    sessions.value = await getChatSessions()
    if (keepId && sessionId.value) return
    sessionId.value = sessions.value[0]?.id ?? null
    if (sessionId.value) await loadMessages()
    else messages.value = []
  } catch { /* request 层已 toast */ }
}

async function loadMessages() {
  if (!sessionId.value) { messages.value = []; return }
  try {
    messages.value = await getChatMessages(sessionId.value)
    await scrollBottom()
  } catch { /* request 层已 toast */ }
}

function newSession() {
  sessionId.value = null
  messages.value = []
  draft.value = ''
}

async function removeSession() {
  if (!sessionId.value) return
  try {
    await ElMessageBox.confirm('删除这个对话及其全部消息？不可恢复。', '删除对话', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    await deleteChatSession(sessionId.value)
    sessionId.value = null
    messages.value = []
    await loadSessions(false)
    ElMessage.success('对话已删除')
  } catch { /* request 层已 toast */ } finally { deleting.value = false }
}

// ---- 发送 ----
async function send() {
  const text = draft.value.trim()
  if (!text || pending.value) return
  pending.value = true
  // 先本地渲染用户消息，回复到达后 push
  messages.value.push({ role: 'user', content: text, createdAt: '' })
  draft.value = ''
  await scrollBottom()
  try {
    const reply = await chatAi(sessionId.value, text)
    sessionId.value = reply.sessionId
    messages.value.push({ role: 'assistant', content: reply.reply, createdAt: '' })
    loadSessions()   // 标题/排序可能变化，静默刷新
  } catch (e) {
    // 优先取后端业务消息（如「请先配置模型」），axios 拒绝时 response.data.message 才是人话
    const err = e as any
    const msg = err?.response?.data?.message || (e instanceof Error && e.message) || '发送失败'
    messages.value.push({ role: 'assistant', content: '⚠ ' + msg, createdAt: '' })
  } finally {
    pending.value = false
    await scrollBottom()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// ---- 轻量渲染：转义后仅支持 加粗/标题/列表/换行（不引入 markdown 依赖） ----
function renderContent(text: string): string {
  let h = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  h = h.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
  h = h.replace(/^\s*#{1,4}\s+(.*)$/gm, '<div class="md-h">$1</div>')
  h = h.replace(/^\s*[-*]\s+(.*)$/gm, '<div class="md-li">• $1</div>')
  h = h.replace(/^\s*\d+[.、)]\s+(.*)$/gm, '<div class="md-li">$1</div>')
  return h.replace(/\n/g, '<br/>')
}

async function scrollBottom() {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

// ---- 语音输入（浏览器原生 Web Speech API，能力不可用则隐藏按钮） ----
const voiceSupported = ref(false)
const listening = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let recognizer: any = null

function toggleVoice() {
  if (listening.value) { recognizer?.stop?.(); return }
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) { ElMessage.warning('当前浏览器不支持语音输入'); return }
  recognizer = new SR()
  recognizer.lang = 'zh-CN'
  recognizer.interimResults = true
  recognizer.continuous = false
  const base = draft.value
  recognizer.onresult = (e: any) => {
    let text = ''
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript
    draft.value = (base ? base + ' ' : '') + text
  }
  recognizer.onend = () => { listening.value = false }
  recognizer.onerror = () => { listening.value = false }
  listening.value = true
  recognizer.start()
}

onMounted(() => {
  voiceSupported.value = !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
  loadSessions()
})
onBeforeUnmount(() => { if (listening.value) recognizer?.stop?.() })
</script>

<style scoped>
.ai-chat {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100vh - 220px);
  min-height: 480px;
}
.ai-chat.mobile { height: calc(100vh - 240px); min-height: 420px; }

.chat-top { display: flex; gap: 8px; align-items: center; }
.session-select { flex: 1; max-width: 420px; }

.chat-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--bg-2);
  border-radius: var(--radius-lg);
}

.bubble-row { display: flex; }
.bubble-row.user { justify-content: flex-end; }
.bubble-row.assistant { justify-content: flex-start; }
.bubble {
  max-width: min(78%, 640px);
  padding: 10px 14px;
  border-radius: var(--radius-lg);
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  white-space: normal;
}
.bubble-row.user .bubble { background: var(--brand); color: #fff; border-bottom-right-radius: 6px; }
.bubble-row.assistant .bubble { background: var(--surface); color: var(--text); border-bottom-left-radius: 6px; box-shadow: var(--shadow-card); }
.bubble :deep(.md-h) { font-weight: 600; margin: 6px 0 2px; color: inherit; }
.bubble :deep(.md-li) { margin: 1px 0; }
.bubble :deep(b) { font-weight: 700; }

.typing { display: inline-flex; gap: 5px; align-items: center; }
.typing span {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--text-4);
  animation: typing 1.2s ease infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%, 60%, 100% { opacity: 0.3; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-3px); } }

.chat-input { display: flex; flex-direction: column; gap: 8px; }
.input-actions { display: flex; align-items: center; gap: 10px; }
.mic-btn {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 50%;
  width: 34px; height: 34px;
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  display: inline-flex; align-items: center; justify-content: center;
  transition: all 0.15s ease;
}
.mic-btn.listening {
  border-color: var(--color-red);
  color: var(--color-red);
  animation: mic-pulse 1.2s ease infinite;
}
@keyframes mic-pulse { 0%, 100% { box-shadow: 0 0 0 0 var(--color-red-soft); } 50% { box-shadow: 0 0 0 6px var(--color-red-soft); } }
.listening-tip { font-size: 12px; color: var(--color-red); }
.disclaimer { flex: 1; font-size: 11px; color: var(--text-4); text-align: right; }
@media (max-width: 768px) {
  .disclaimer { display: none; }
  .bubble { max-width: 88%; font-size: 13px; }
}
</style>
