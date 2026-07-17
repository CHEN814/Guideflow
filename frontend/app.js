/* Guideflow frontend (two-column + auth + true SSE). */
// Use ?? so API_BASE '' (same-origin under /app/) is not replaced by 127.0.0.1.
const API_BASE = window.API_BASE ?? 'http://127.0.0.1:8001';

const els = {
  appRoot: document.getElementById('appRoot'),
  sidebar: document.getElementById('sidebar'),
  historyList: document.getElementById('historyList'),
  chatLog: document.getElementById('chatLog'),
  followUpInput: document.getElementById('followUpInput'),
  askBtn: document.getElementById('askBtn'),
  newChatBtn: document.getElementById('newChatBtn'),
  collapseSidebarBtn: document.getElementById('collapseSidebarBtn'),
  expandSidebarBtn: document.getElementById('expandSidebarBtn'),
  sidebarBackdrop: document.getElementById('sidebarBackdrop'),
  userArea: document.getElementById('userArea'),
  loginOpenBtn: document.getElementById('loginOpenBtn'),
  authModal: document.getElementById('authModal'),
  authForm: document.getElementById('authForm'),
  authTitle: document.getElementById('authTitle'),
  authEmail: document.getElementById('authEmail'),
  authPassword: document.getElementById('authPassword'),
  authPasswordLabel: document.getElementById('authPasswordLabel'),
  authNewPassword: document.getElementById('authNewPassword'),
  authNewPasswordLabel: document.getElementById('authNewPasswordLabel'),
  authPwToggle: document.getElementById('authPwToggle'),
  authNewPwToggle: document.getElementById('authNewPwToggle'),
  authError: document.getElementById('authError'),
  authHint: document.getElementById('authHint'),
  authSubmitBtn: document.getElementById('authSubmitBtn'),
  authToggleModeBtn: document.getElementById('authToggleModeBtn'),
  authForgotBtn: document.getElementById('authForgotBtn'),
  authCloseBtn: document.getElementById('authCloseBtn'),
  citePopover: document.getElementById('citePopover'),
  toolsBtn: document.getElementById('toolsBtn'),
  toolsMenu: document.getElementById('toolsMenu'),
  shareChatBtn: document.getElementById('shareChatBtn'),
  composerBox: document.getElementById('composerBox'),
  expandInputBtn: document.getElementById('expandInputBtn'),
};

const ICON = {
  copy: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>`,
  regen: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>`,
  up: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 11v10"/><path d="M15 21H9a2 2 0 0 1-2-2v-7l5.2-8.1a1.6 1.6 0 0 1 2.9 1.2L14 10h5.4a2 2 0 0 1 1.9 2.6l-1.5 6A2 2 0 0 1 17.9 21H15z"/></svg>`,
  down: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 13V3"/><path d="M9 3h6a2 2 0 0 1 2 2v7l-5.2 8.1a1.6 1.6 0 0 1-2.9-1.2L10 14H4.6a2 2 0 0 1-1.9-2.6l1.5-6A2 2 0 0 1 6.1 3H9z"/></svg>`,
  share: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="M8.4 13.3l7.2 4.4M15.6 6.3l-7.2 4.4"/></svg>`,
  shareChat: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v10"/><path d="M8 7l4-4 4 4"/><path d="M5 12v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>`,
  check: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 13l4 4L19 7"/></svg>`,
};

const SUGGESTIONS = [
  'DLBCL 一线治疗推荐？',
  'GCB 与 ABC 亚型差异',
  'TP53 对预后的影响',
  '什么时候考虑 CNS prophylaxis？',
];

const state = {
  user: null,
  conversations: [],
  activeConversationId: null,
  messages: [], // {id, role, content, payload, feedback}
  lastPayload: null,
  isSubmitting: false,
  authMode: 'login', // login | register | reset
  composerExpanded: false,
  authOverlayDown: false,
  citeHideTimer: null,
  citePinned: false,
  sidebarCollapsed: localStorage.getItem('gf_sidebar_collapsed') === '1',
  abortController: null,
};

const ACTIVE_CONV_KEY = 'gf_active_conversation_id';
const DRAFT_KEY = 'gf_chat_draft';
const LOCAL_CONV_KEY = 'gf_local_conversations';
const ICON_EYE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/></svg>`;
const ICON_EYE_OFF = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 10.6a2.5 2.5 0 0 0 3.5 3.5"/><path d="M9.9 5.2A11.3 11.3 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-4.1 4.8"/><path d="M6.1 6.1C3.9 7.8 2 12 2 12s3.5 6 10 6c1.3 0 2.5-.2 3.6-.6"/></svg>`;

function isLocalConversationId(id) {
  return typeof id === 'string' && id.startsWith('local-');
}

function newLocalConversationId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `local-${crypto.randomUUID()}`;
  }
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function loadLocalConversations() {
  try {
    const list = JSON.parse(sessionStorage.getItem(LOCAL_CONV_KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function saveLocalConversations(list) {
  try {
    sessionStorage.setItem(LOCAL_CONV_KEY, JSON.stringify(list));
  } catch { /* ignore */ }
}

function snapshotMessagesForStore(messages) {
  return (messages || [])
    .filter((m) => !m.pending)
    .map((m) => ({
      id: m.id || null,
      role: m.role,
      content: m.content,
      payload: m.payload || null,
      feedback: m.feedback || null,
    }));
}

function conversationTitleFromMessages(messages) {
  const firstUser = (messages || []).find((m) => m.role === 'user' && m.content);
  const raw = String(firstUser?.content || '新对话').trim().replace(/\s+/g, ' ');
  return (raw.slice(0, 40) || '新对话');
}

function localConversationsAsSummaries(list) {
  return (list || []).map((c) => ({
    id: c.id,
    title: c.title || '新对话',
    updated_at: c.updated_at,
    created_at: c.updated_at,
    message_count: (c.messages || []).length,
  }));
}

function syncLocalConversationsToState() {
  const list = loadLocalConversations();
  list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  state.conversations = localConversationsAsSummaries(list);
}

function upsertLocalConversationFromState() {
  if (state.user) return;
  const messages = snapshotMessagesForStore(state.messages);
  if (!messages.length) return;

  let id = state.activeConversationId;
  if (!isLocalConversationId(id)) {
    id = newLocalConversationId();
    state.activeConversationId = id;
  }

  const list = loadLocalConversations();
  const prev = list.find((c) => c.id === id);
  const autoTitle = conversationTitleFromMessages(messages);
  const prevAuto = conversationTitleFromMessages(prev?.messages || []);
  const keepRename = Boolean(prev?.title && prev.title !== '新对话' && prev.title !== prevAuto);
  const entry = {
    id,
    title: keepRename ? prev.title : autoTitle,
    updated_at: new Date().toISOString(),
    messages,
    lastPayload: state.lastPayload,
  };
  const idx = list.findIndex((c) => c.id === id);
  if (idx >= 0) list[idx] = entry;
  else list.unshift(entry);

  list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  saveLocalConversations(list);
  state.conversations = localConversationsAsSummaries(list);
}

function openLocalConversation(id) {
  const list = loadLocalConversations();
  const conv = list.find((c) => c.id === id);
  if (!conv) return;
  state.activeConversationId = conv.id;
  state.messages = (conv.messages || []).map((m) => ({ ...m }));
  state.lastPayload = conv.lastPayload || null;
  persistChatState();
  renderHistory();
  renderChat();
}

function renameLocalConversation(id, title) {
  const trimmed = String(title || '').trim().slice(0, 200);
  if (!trimmed) return;
  const list = loadLocalConversations();
  const conv = list.find((c) => c.id === id);
  if (!conv) return;
  conv.title = trimmed;
  conv.updated_at = new Date().toISOString();
  saveLocalConversations(list);
  syncLocalConversationsToState();
  renderHistory();
}

function deleteLocalConversation(id) {
  const list = loadLocalConversations().filter((c) => c.id !== id);
  saveLocalConversations(list);
  syncLocalConversationsToState();
  if (state.activeConversationId === id) newChat({ skipSave: true });
  else renderHistory();
}

function detachLocalActiveConversation() {
  if (isLocalConversationId(state.activeConversationId)) {
    state.activeConversationId = null;
  }
}

function persistChatState() {
  try {
    if (!state.user) upsertLocalConversationFromState();
    if (state.activeConversationId && !isLocalConversationId(state.activeConversationId)) {
      localStorage.setItem(ACTIVE_CONV_KEY, state.activeConversationId);
    } else {
      localStorage.removeItem(ACTIVE_CONV_KEY);
    }
    const draft = {
      conversationId: state.activeConversationId,
      messages: snapshotMessagesForStore(state.messages),
      lastPayload: state.lastPayload,
    };
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch { /* ignore */ }
}

function loadDraft() {
  try {
    return JSON.parse(sessionStorage.getItem(DRAFT_KEY) || 'null');
  } catch {
    return null;
  }
}

async function restoreChatAfterLoad() {
  const savedId = localStorage.getItem(ACTIVE_CONV_KEY);
  if (state.user && savedId && !isLocalConversationId(savedId)) {
    const exists = state.conversations.some((c) => c.id === savedId);
    if (exists) {
      await openConversation(savedId);
      return;
    }
    localStorage.removeItem(ACTIVE_CONV_KEY);
  }
  const draft = loadDraft();
  if (!draft?.messages?.length) {
    if (!state.user) {
      syncLocalConversationsToState();
      renderHistory();
    }
    return;
  }
  if (draft.conversationId && state.user && !isLocalConversationId(draft.conversationId)) {
    const exists = state.conversations.some((c) => c.id === draft.conversationId);
    if (exists) {
      await openConversation(draft.conversationId);
      return;
    }
  }
  state.activeConversationId = draft.conversationId || null;
  if (state.user) detachLocalActiveConversation();
  state.messages = draft.messages;
  state.lastPayload = draft.lastPayload || null;
  if (!state.user) upsertLocalConversationFromState();
  renderHistory();
  renderChat();
}

function api(path, options = {}) {
  return fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (s) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[s]));
}

function resolveImageUrl(url) {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url.startsWith('/') ? url : `/${url}`}`;
}

function renderMarkdown(md) {
  const raw = String(md || '');
  let html;
  try {
    html = window.marked?.parse ? window.marked.parse(raw, { breaks: true }) : raw;
  } catch {
    html = escapeHtml(raw).replace(/\n/g, '<br>');
  }
  return window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
}

const mobileMQ = window.matchMedia('(max-width:900px)');

function isMobileLayout() {
  return mobileMQ.matches;
}

function setSidebarCollapsed(collapsed, { persist = true } = {}) {
  state.sidebarCollapsed = collapsed;
  els.appRoot.classList.toggle('collapsed', collapsed);
  els.expandSidebarBtn.hidden = !collapsed;
  if (els.sidebarBackdrop) {
    els.sidebarBackdrop.hidden = collapsed || !isMobileLayout();
  }
  if (persist) {
    localStorage.setItem('gf_sidebar_collapsed', collapsed ? '1' : '0');
  }
  if (!collapsed) requestAnimationFrame(updateHistoryScrollFade);
}

function closeSidebarOnMobile() {
  if (isMobileLayout() && !state.sidebarCollapsed) {
    setSidebarCollapsed(true, { persist: false });
  }
}

function showAuthError(msg) {
  els.authError.hidden = !msg;
  els.authError.textContent = typeof msg === 'string' ? msg : (msg?.detail || '请求失败');
}

function setAuthHint(msg) {
  if (!els.authHint) return;
  els.authHint.hidden = !msg;
  els.authHint.textContent = msg || '';
}

function openAuthModal(mode = 'login') {
  state.authMode = mode;
  const isReset = mode === 'reset';
  const isLogin = mode === 'login';
  els.authTitle.textContent = isReset ? '重置密码' : (isLogin ? '登录' : '注册');
  els.authSubmitBtn.textContent = isReset ? '更新密码' : (isLogin ? '登录' : '注册');
  els.authToggleModeBtn.textContent = isLogin ? '没有账号？注册' : '已有账号？登录';
  els.authToggleModeBtn.hidden = isReset;
  if (els.authForgotBtn) els.authForgotBtn.hidden = isReset;
  if (els.authPasswordLabel) els.authPasswordLabel.hidden = isReset;
  if (els.authNewPasswordLabel) els.authNewPasswordLabel.hidden = !isReset;
  els.authPassword.required = !isReset;
  if (els.authNewPassword) els.authNewPassword.required = isReset;
  setAuthHint(isReset
    ? '输入注册邮箱与新密码。当前为本地重置（未接入邮件验证）；生产环境请关闭 AUTH_ALLOW_PASSWORD_RESET。'
    : '');
  showAuthError('');
  els.authModal.hidden = false;
  els.authEmail.focus();
}

function closeAuthModal() {
  els.authModal.hidden = true;
}

function formatApiDetail(data) {
  if (!data) return '请求失败';
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join('；') || '请求失败';
  }
  return data.message || '请求失败';
}

async function refreshMe() {
  try {
    const resp = await api('/api/auth/me');
    if (!resp.ok) {
      state.user = null;
    } else {
      const data = await resp.json();
      // FastAPI may return JSON null when unauthenticated
      state.user = data && data.email ? data : null;
    }
  } catch {
    state.user = null;
  }
  renderUserArea();
  if (state.user) {
    detachLocalActiveConversation();
    await loadConversations();
  } else {
    syncLocalConversationsToState();
    renderHistory();
  }
  await restoreChatAfterLoad();
}

function renderUserArea() {
  if (state.user) {
    els.userArea.innerHTML = `
      <div class="user-chip" id="userMenuBtn">
        <span class="email">${escapeHtml(state.user.email)}</span>
        <span class="sub">点击退出登录</span>
      </div>`;
    document.getElementById('userMenuBtn')?.addEventListener('click', async () => {
      if (!confirm('确定要退出登录吗？')) return;
      await api('/api/auth/logout', { method: 'POST', body: '{}' });
      state.user = null;
      state.activeConversationId = null;
      state.messages = [];
      state.lastPayload = null;
      localStorage.removeItem(ACTIVE_CONV_KEY);
      sessionStorage.removeItem(DRAFT_KEY);
      syncLocalConversationsToState();
      renderUserArea();
      renderHistory();
      renderChat();
      openAuthModal('login');
    });
  } else {
    els.userArea.innerHTML = `<button class="user-chip" id="loginOpenBtn">登录 / 注册</button>`;
    document.getElementById('loginOpenBtn')?.addEventListener('click', () => openAuthModal('login'));
  }
}

function groupConversations(list) {
  const now = Date.now();
  const day = 86400000;
  const groups = [
    { key: '今天', items: [] },
    { key: '7 天内', items: [] },
    { key: '30 天内', items: [] },
    { key: '更早', items: [] },
  ];
  for (const c of list) {
    const t = new Date(c.updated_at).getTime();
    const age = now - t;
    if (age < day) groups[0].items.push(c);
    else if (age < 7 * day) groups[1].items.push(c);
    else if (age < 30 * day) groups[2].items.push(c);
    else groups[3].items.push(c);
  }
  return groups.filter((g) => g.items.length);
}

async function loadConversations() {
  if (!state.user) return;
  try {
    const resp = await api('/api/conversations');
    if (resp.status === 401) {
      state.user = null;
      renderUserArea();
      syncLocalConversationsToState();
      renderHistory();
      return;
    }
    if (!resp.ok) {
      els.historyList.innerHTML = `<div class="muted small" style="padding:10px">历史加载失败（${resp.status}）</div>`;
      return;
    }
    state.conversations = await resp.json();
    renderHistory();
  } catch {
    els.historyList.innerHTML = `<div class="muted small" style="padding:10px">历史加载失败，请检查后端是否运行</div>`;
  }
}

function updateHistoryScrollFade() {
  const wrap = els.historyList?.closest('.history-wrap');
  const list = els.historyList;
  if (!wrap || !list) return;
  const canScroll = list.scrollHeight > list.clientHeight + 2;
  const atBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 4;
  wrap.classList.toggle('can-scroll-more', canScroll && !atBottom);
}

function bindHistoryScrollFade() {
  const list = els.historyList;
  if (!list || list.dataset.scrollFadeBound) return;
  list.dataset.scrollFadeBound = '1';
  list.addEventListener('scroll', updateHistoryScrollFade, { passive: true });
  window.addEventListener('resize', updateHistoryScrollFade);
}

function renderHistory() {
  if (!state.conversations.length) {
    els.historyList.innerHTML = `<div class="muted small" style="padding:10px">暂无历史对话</div>`;
    updateHistoryScrollFade();
    return;
  }
  const groups = groupConversations(state.conversations);
  els.historyList.innerHTML = groups.map((g) => `
    <div class="history-group">${escapeHtml(g.key)}</div>
    ${g.items.map((c) => `
      <div class="history-item ${c.id === state.activeConversationId ? 'active' : ''}" data-id="${escapeHtml(c.id)}">
        <div class="title">${escapeHtml(c.title || '新对话')}</div>
        <button class="more" data-more="${escapeHtml(c.id)}" title="更多">⋯</button>
      </div>`).join('')}
  `).join('');

  els.historyList.querySelectorAll('.history-item').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-more]')) return;
      openConversation(el.dataset.id);
      closeSidebarOnMobile();
    });
  });
  els.historyList.querySelectorAll('[data-more]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      openHistoryMenu(btn.dataset.more, e.clientX, e.clientY);
    });
  });
  bindHistoryScrollFade();
  requestAnimationFrame(updateHistoryScrollFade);
}

function openHistoryMenu(id, x, y) {
  document.getElementById('ctxMenu')?.remove();
  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.id = 'ctxMenu';
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.innerHTML = `
    <button data-act="rename">重命名</button>
    <button data-act="delete">删除</button>`;
  document.body.appendChild(menu);
  const close = () => { menu.remove(); document.removeEventListener('click', close); };
  setTimeout(() => document.addEventListener('click', close), 0);
  menu.querySelector('[data-act="rename"]').onclick = async () => {
    const title = prompt('新标题');
    if (!title?.trim()) return;
    if (isLocalConversationId(id)) {
      renameLocalConversation(id, title);
      return;
    }
    await api(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title: title.trim() }) });
    await loadConversations();
  };
  menu.querySelector('[data-act="delete"]').onclick = async () => {
    if (!confirm('确认删除该对话？')) return;
    if (isLocalConversationId(id)) {
      deleteLocalConversation(id);
      return;
    }
    await api(`/api/conversations/${id}`, { method: 'DELETE' });
    if (state.activeConversationId === id) newChat({ skipSave: true });
    await loadConversations();
  };
}

async function openConversation(id) {
  if (isLocalConversationId(id)) {
    openLocalConversation(id);
    return;
  }
  const resp = await api(`/api/conversations/${id}`);
  if (!resp.ok) return;
  const data = await resp.json();
  state.activeConversationId = data.id;
  state.messages = (data.messages || []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    payload: m.payload,
    feedback: m.feedback,
  }));
  const lastAssistant = [...state.messages].reverse().find((m) => m.role === 'assistant');
  state.lastPayload = lastAssistant?.payload || null;
  persistChatState();
  renderHistory();
  renderChat();
}

function newChat({ skipSave = false } = {}) {
  if (!skipSave && !state.user) {
    upsertLocalConversationFromState();
  }
  state.activeConversationId = null;
  state.messages = [];
  state.lastPayload = null;
  if (state.abortController) state.abortController.abort();
  localStorage.removeItem(ACTIVE_CONV_KEY);
  sessionStorage.removeItem(DRAFT_KEY);
  if (!state.user) syncLocalConversationsToState();
  renderHistory();
  renderChat();
  closeSidebarOnMobile();
  els.followUpInput.focus();
}

function updateShareChatBtn() {
  if (!els.shareChatBtn) return;
  const hasAssistant = state.messages.some((m) => m.role === 'assistant' && !m.pending);
  els.shareChatBtn.hidden = !hasAssistant;
}

function renderChat() {
  if (!state.messages.length) {
    els.chatLog.innerHTML = `
      <div class="empty-state">
        <h2>面向 DLBCL 的 NCCN 指南问答</h2>
        <p>答案受证据约束，支持流程图、参考文献悬浮与 Trace 调试。</p>
        <div class="template-row">
          ${SUGGESTIONS.map((q) => `<button class="template-pill" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join('')}
        </div>
      </div>`;
    els.chatLog.querySelectorAll('[data-q]').forEach((btn) => {
      btn.addEventListener('click', () => askQuestion(btn.dataset.q));
    });
    updateShareChatBtn();
    return;
  }
  els.chatLog.innerHTML = state.messages.map((m, idx) => renderMessage(m, idx)).join('');
  bindMessageActions();
  bindCitations();
  bindFigures();
  updateShareChatBtn();
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function renderMessage(message, idx) {
  if (message.role === 'user') {
    return `<div class="message user"><div class="tag">用户提问</div><div>${escapeHtml(message.content)}</div></div>`;
  }
  if (message.pending) {
    const steps = Array.isArray(message.statusSteps) ? message.statusSteps : [];
    const stepsHtml = steps.length
      ? `<ul class="status-steps">${steps.map((s, i) => {
          const done = i < steps.length - 1;
          return `<li class="${done ? 'done' : 'active'}"><span class="dot"></span><span>${escapeHtml(s.label || s.stage || '')}</span></li>`;
        }).join('')}</ul>`
      : '';
    const current = steps.length ? steps[steps.length - 1].label : '正在检索与生成回答…';
    return `
      <div class="message assistant" data-msg-idx="${idx}">
        <div class="tag">AI 回答</div>
        <div class="answer">
          <div class="typing-indicator">
            <span class="spinner" aria-hidden="true"></span>
            <span class="status-current">${escapeHtml(current)}</span>
          </div>
          ${stepsHtml}
        </div>
      </div>`;
  }
  const payload = message.payload || state.lastPayload || {};
  const body = renderAnswerBody(payload, message.content);
  const feedback = message.feedback || '';
  const tag = answerKindLabel(payload.answer_kind);
  return `
    <div class="message assistant" data-msg-idx="${idx}" data-msg-id="${escapeHtml(message.id || '')}">
      <div class="tag">${escapeHtml(tag)}</div>
      <div class="answer">${body}</div>
      <div class="msg-actions">
        <button type="button" data-act="copy" title="复制" aria-label="复制">${ICON.copy}</button>
        <button type="button" data-act="regen" title="重说" aria-label="重说">${ICON.regen}</button>
        <button type="button" data-act="up" class="${feedback === 'up' ? 'active' : ''}" title="点赞" aria-label="点赞">${ICON.up}</button>
        <button type="button" data-act="down" class="${feedback === 'down' ? 'active' : ''}" title="点踩" aria-label="点踩">${ICON.down}</button>
        <button type="button" data-act="share" title="分享此回答" aria-label="分享此回答">${ICON.share}</button>
      </div>
    </div>`;
}

function renderAnswerBody(payload, fallbackText) {
  const paragraphs = (payload.answer_paragraphs && payload.answer_paragraphs.length)
    ? payload.answer_paragraphs
    : [payload.answer_markdown || fallbackText || ''];
  const figures = payload.figures || [];
  const anchored = new Map();
  const unanchored = [];
  for (const fig of figures) {
    if (fig.anchor_paragraph != null) {
      const list = anchored.get(fig.anchor_paragraph) || [];
      list.push(fig);
      anchored.set(fig.anchor_paragraph, list);
    } else unanchored.push(fig);
  }
  let html = paragraphs.map((p, idx) => {
    const figs = (anchored.get(idx) || []).map((f, i) => renderFigureCard(f, `${idx}-${i}`)).join('');
    return `<div class="answer-block">${decorateCitations(renderMarkdown(p), payload)}${figs}</div>`;
  }).join('');
  if (unanchored.length) {
    html += `<div class="answer-block"><h3>相关流程图</h3>${unanchored.map((f, i) => renderFigureCard(f, `u-${i}`)).join('')}</div>`;
  }
  html += renderReferences(payload);
  return html;
}

function renderFigureCard(fig, key) {
  const compact = resolveImageUrl(fig.image_url || fig.full_image_url);
  const full = resolveImageUrl(fig.full_image_url || fig.image_url);
  if (!compact) return '';
  const label = fig.page_code || `pdf_page=${fig.pdf_page}`;
  const hasFull = full && full !== compact;
  return `
    <figure class="figure-card" data-fig-key="${escapeHtml(key)}">
      <div class="fig-head">
        <span>${escapeHtml(label)}${fig.source_index ? ` · [S${fig.source_index}]` : ''}</span>
        <button type="button" class="btn ghost" data-fig-open="${escapeHtml(full || compact)}" data-fig-label="${escapeHtml(label)}">${hasFull ? '放大（含脚注）' : '放大'}</button>
      </div>
      <img src="${escapeHtml(compact)}" alt="${escapeHtml(label)}" data-fig-open="${escapeHtml(full || compact)}" />
      ${fig.caption ? `<div class="fig-cap">${escapeHtml(fig.caption)}</div>` : ''}
    </figure>`;
}

function decorateCitations(html, payload) {
  const refs = payload.attached_references || [];
  return html
    .replace(/\[S(\d+)\]/gi, (_, n) => {
      const idx = Number(n) - 1;
      return `<button class="cite" data-cite="S" data-index="${idx}">S${n}</button>`;
    })
    .replace(/\[G(\d+)\]/gi, (_, n) => {
      const idx = Number(n) - 1;
      return `<button class="cite" data-cite="G" data-index="${idx}">G${n}</button>`;
    })
    .replace(/\[(\d{1,3})\]/g, (m, n) => {
      const hit = refs.find((r) => String(r.ref_number) === String(n));
      if (!hit) return m;
      return `<button class="cite" data-cite="R" data-ref="${escapeHtml(String(n))}">${n}</button>`;
    });
}

function answerKindLabel(kind) {
  if (kind === 'chitchat') return 'AI 回答 · 闲聊';
  if (kind === 'general_medical') return 'AI 回答 · 非指南内容';
  return 'AI 回答 · 证据约束';
}

function renderReferences(payload) {
  const sources = payload.sources || [];
  const refs = payload.attached_references || [];
  if (!sources.length && !refs.length) return '';
  const items = [];
  sources.forEach((s, i) => {
    items.push({
      title: s.printed_page_code || s.source_id || `Source ${i + 1}`,
      meta: `${s.page_type || 'source'}${s.section ? ` · ${s.section}` : ''}${s.pdf_page ? ` · p.${s.pdf_page}` : ''}`,
      badge: s.page_type === 'clinical_guideline' ? 'Guideline' : (s.page_type || 'Source'),
    });
  });
  refs.forEach((r) => {
    items.push({
      title: `[${r.ref_number}] ${(r.text || '').slice(0, 160)}`,
      meta: [r.pmid ? `PMID ${r.pmid}` : '', r.doi ? `DOI ${r.doi}` : ''].filter(Boolean).join(' · ') || 'Reference',
      badge: 'Reference',
      url: r.url,
    });
  });
  return `
    <details class="refs-block">
      <summary><span>References</span><span class="muted small">${items.length}</span></summary>
      ${items.map((it, i) => `
        <div class="ref-item">
          <div class="rtitle">${i + 1}. ${it.url ? `<a href="${escapeHtml(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a>` : escapeHtml(it.title)}</div>
          <div class="rmeta"><span>${escapeHtml(it.meta)}</span><span class="badge">${escapeHtml(it.badge)}</span></div>
        </div>`).join('')}
    </details>`;
}

function bindFigures() {
  els.chatLog.querySelectorAll('[data-fig-open]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      openLightbox(el.getAttribute('data-fig-open'), el.getAttribute('data-fig-label') || '');
    });
  });
}

function openLightbox(src, label) {
  const overlay = document.createElement('div');
  overlay.className = 'lightbox';
  overlay.innerHTML = `<img src="${escapeHtml(src)}" alt="${escapeHtml(label)}" />`;
  overlay.addEventListener('click', () => overlay.remove());
  document.body.appendChild(overlay);
}

function bindCitations() {
  const payload = state.lastPayload || {};
  const pop = els.citePopover;
  if (!pop) return;

  const clearHide = () => {
    if (state.citeHideTimer) {
      clearTimeout(state.citeHideTimer);
      state.citeHideTimer = null;
    }
  };
  const hidePopover = () => {
    clearHide();
    pop.hidden = true;
    state.citePinned = false;
  };
  const scheduleHide = () => {
    if (state.citePinned) return;
    clearHide();
    state.citeHideTimer = setTimeout(() => {
      pop.hidden = true;
      state.citeHideTimer = null;
    }, 160);
  };
  const scrollToRefs = () => {
    hidePopover();
    document.querySelector('.refs-block')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const showFor = (btn, { pin = false } = {}) => {
    clearHide();
    state.citePinned = !!pin;
    const type = btn.dataset.cite;
    const citeKey = `${type}:${btn.dataset.index ?? ''}:${btn.dataset.ref ?? ''}`;
    pop.dataset.citeKey = citeKey;
    let html = '';
    let seeCount = (payload.sources || []).length + (payload.attached_references || []).length;
    if (type === 'S') {
      const s = (payload.sources || [])[Number(btn.dataset.index)] || {};
      html = `
        <div class="ref-head"><span class="k">Reference</span><button type="button" class="see" data-see-all>See All (${seeCount})</button></div>
        <div class="ref-title">${escapeHtml(s.printed_page_code || s.source_id || 'Source')}</div>
        <div class="ref-meta"><span>NCCN B-Cell Lymphomas</span><span class="badge">${escapeHtml(s.page_type || 'Guideline')}</span></div>
        <div class="muted small" style="margin-top:8px">${escapeHtml((s.text || s.section || '').slice(0, 180))}</div>`;
    } else if (type === 'G') {
      const g = (payload.graph_triples || [])[Number(btn.dataset.index)] || {};
      html = `
        <div class="ref-head"><span class="k">Graph</span><button type="button" class="see" data-see-all>See All</button></div>
        <div class="ref-title">${escapeHtml(g.subject_name || '')} → ${escapeHtml(g.relation || '')} → ${escapeHtml(g.object_name || '')}</div>
        <div class="ref-meta"><span>confidence ${Number(g.confidence || 0).toFixed(2)}</span><span class="badge">${escapeHtml(g.validation_status || 'graph')}</span></div>`;
    } else {
      const r = (payload.attached_references || []).find((x) => String(x.ref_number) === String(btn.dataset.ref)) || {};
      html = `
        <div class="ref-head"><span class="k">Reference</span><button type="button" class="see" data-see-all>See All (${seeCount})</button></div>
        <div class="ref-title">${escapeHtml(`[${r.ref_number || ''}] ${(r.text || '').slice(0, 120)}`)}</div>
        <div class="ref-meta"><span>${escapeHtml(r.pmid ? `PMID ${r.pmid}` : 'Literature')}</span><span class="badge">Reference</span></div>`;
    }
    pop.innerHTML = html;
    pop.hidden = false;
    const rect = btn.getBoundingClientRect();
    const left = Math.min(window.innerWidth - 380, Math.max(8, rect.left));
    const top = Math.min(window.innerHeight - 200, rect.bottom + 8);
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
    pop.querySelector('[data-see-all]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      scrollToRefs();
    });
  };

  if (!pop.dataset.bound) {
    pop.dataset.bound = '1';
    pop.addEventListener('mouseenter', clearHide);
    pop.addEventListener('mouseleave', scheduleHide);
    document.addEventListener('pointerdown', (e) => {
      if (pop.hidden) return;
      const t = e.target;
      if (pop.contains(t) || (t instanceof Element && t.closest('.cite'))) return;
      hidePopover();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !pop.hidden) hidePopover();
    });
  }

  els.chatLog.querySelectorAll('.cite').forEach((btn) => {
    btn.addEventListener('mouseenter', () => {
      if (!state.citePinned) showFor(btn, { pin: false });
    });
    btn.addEventListener('mouseleave', scheduleHide);
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const citeKey = `${btn.dataset.cite}:${btn.dataset.index ?? ''}:${btn.dataset.ref ?? ''}`;
      if (!pop.hidden && state.citePinned && pop.dataset.citeKey === citeKey) {
        hidePopover();
        return;
      }
      showFor(btn, { pin: true });
    });
  });
}

function resizeComposer({ forceCompact = false } = {}) {
  const el = els.followUpInput;
  if (!el) return;
  if (state.composerExpanded) {
    el.style.height = '180px';
    return;
  }
  if (forceCompact) {
    el.style.height = '40px';
    return;
  }
  el.style.height = 'auto';
  el.style.height = `${Math.min(160, Math.max(40, el.scrollHeight))}px`;
}

function setComposerExpanded(expanded) {
  state.composerExpanded = !!expanded;
  els.composerBox?.classList.toggle('expanded', state.composerExpanded);
  if (els.expandInputBtn) {
    els.expandInputBtn.title = state.composerExpanded ? '收起输入' : '展开输入';
    els.expandInputBtn.setAttribute('aria-label', els.expandInputBtn.title);
  }
  // Collapsing always returns to the compact initial size, regardless of content length.
  resizeComposer({ forceCompact: !state.composerExpanded });
}

function bindPasswordToggle(btn, input) {
  if (!btn || !input) return;
  const sync = () => {
    const showing = input.type === 'text';
    btn.innerHTML = showing ? ICON_EYE_OFF : ICON_EYE;
    btn.title = showing ? '隐藏密码' : '显示密码';
    btn.setAttribute('aria-label', btn.title);
    btn.setAttribute('aria-pressed', showing ? 'true' : 'false');
  };
  sync();
  btn.addEventListener('click', () => {
    input.type = input.type === 'password' ? 'text' : 'password';
    sync();
  });
}

function flashActionIcon(btn, tempKey, tempLabel, restoreHtml, restoreLabel, ms) {
  btn.innerHTML = ICON[tempKey];
  btn.title = tempLabel;
  btn.setAttribute('aria-label', tempLabel);
  clearTimeout(btn._flashTimer);
  btn._flashTimer = setTimeout(() => {
    btn.innerHTML = restoreHtml;
    btn.title = restoreLabel;
    btn.setAttribute('aria-label', restoreLabel);
  }, ms);
}

/** Clipboard API 仅在安全上下文（HTTPS / localhost）可用；HTTP 部署用 execCommand 回退。 */
async function copyTextToClipboard(text) {
  const value = String(text ?? '');
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return true;
  }
  const ta = document.createElement('textarea');
  ta.value = value;
  ta.setAttribute('readonly', '');
  ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, ta.value.length);
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  if (!ok) throw new Error('clipboard unavailable');
  return true;
}

function buildShareUrl(token, { messageId = null } = {}) {
  const base = `${location.origin}${location.pathname.replace(/index\.html.?$/, '')}share.html`;
  const params = new URLSearchParams({ token });
  // Same-origin (''): omit api= so share page also auto-detects. Else pass absolute API.
  if (API_BASE) params.set('api', API_BASE);
  if (messageId) params.set('message_id', messageId);
  return `${base}?${params.toString()}`;
}

async function createShareLink({ messageId = null } = {}) {
  if (!state.user) {
    openAuthModal('login');
    return null;
  }
  let convId = state.activeConversationId;
  if (!convId) {
    alert('当前对话尚未保存到云端。请确认已登录，并在登录后重新提问一次，再分享。');
    return null;
  }
  const resp = await api(`/api/conversations/${convId}/share`, { method: 'POST', body: '{}' });
  if (resp.status === 401) {
    state.user = null;
    renderUserArea();
    openAuthModal('login');
    return null;
  }
  if (!resp.ok) {
    alert('分享失败');
    return null;
  }
  const data = await resp.json();
  return buildShareUrl(data.token, { messageId });
}

async function copyShareLink(url, btn, restoreHtml, restoreLabel = '分享') {
  try {
    await copyTextToClipboard(url);
    if (btn) flashActionIcon(btn, 'check', '已复制链接', restoreHtml, restoreLabel, 1200);
  } catch {
    prompt('分享链接（请手动复制）:', url);
  }
}

function bindMessageActions() {
  els.chatLog.querySelectorAll('.message.assistant').forEach((node) => {
    const idx = Number(node.dataset.msgIdx);
    const msg = state.messages[idx];
    if (!msg) return;
    node.querySelectorAll('[data-act]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const act = btn.dataset.act;
        if (act === 'copy') {
          const text = msg.payload?.answer_markdown || msg.content || '';
          try {
            await copyTextToClipboard(text);
            flashActionIcon(btn, 'check', '已复制', ICON.copy, '复制', 1000);
          } catch {
            alert('复制失败，请手动选择文本复制');
          }
        } else if (act === 'regen') {
          const userMsg = [...state.messages].slice(0, idx).reverse().find((m) => m.role === 'user');
          if (userMsg) askQuestion(userMsg.content, { regenerate: true });
        } else if (act === 'up' || act === 'down') {
          const value = msg.feedback === act ? null : act;
          // 未登录也可本地点赞/点踩；已登录且消息已落库时同步到服务端
          if (state.user && msg.id) {
            const resp = await api(`/api/messages/${msg.id}/feedback`, {
              method: 'POST',
              body: JSON.stringify({ value }),
            });
            if (!resp.ok) {
              alert('反馈提交失败，请稍后重试');
              return;
            }
          }
          msg.feedback = value;
          persistChatState();
          renderChat();
        } else if (act === 'share') {
          const url = await createShareLink({ messageId: msg.id || null });
          if (!url) return;
          await copyShareLink(url, btn, ICON.share, '分享此回答');
        }
      });
    });
  });
}

async function askQuestion(question, meta = {}) {
  const q = String(question || '').trim();
  if (!q || state.isSubmitting) return;
  state.isSubmitting = true;
  els.askBtn.disabled = true;
  if (els.followUpInput) els.followUpInput.value = '';
  setComposerExpanded(false);

  if (!meta.regenerate) {
    state.messages.push({ role: 'user', content: q });
  } else {
    // Drop trailing assistant message when regenerating.
    if (state.messages.at(-1)?.role === 'assistant') state.messages.pop();
  }
  const assistant = {
    role: 'assistant',
    content: '',
    payload: null,
    feedback: null,
    pending: true,
    statusSteps: [],
  };
  state.messages.push(assistant);
  renderChat();

  if (state.abortController) state.abortController.abort();
  state.abortController = new AbortController();

  try {
    const history = state.messages
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && !m.pending))
      .slice(0, -2) // exclude the just-appended user + pending assistant
      .slice(-6)
      .map((m) => ({
        role: m.role,
        content: (m.content || m.payload?.answer_markdown || '').slice(0, 1200),
      }))
      .filter((m) => m.content && m.content.trim());
    const conversationId = isLocalConversationId(state.activeConversationId)
      ? null
      : (state.activeConversationId || null);
    const resp = await api('/api/ask', {
      method: 'POST',
      body: JSON.stringify({
        question: q,
        stream: true,
        trace: true,
        conversation_id: conversationId,
        history,
      }),
      signal: state.abortController.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const ctype = resp.headers.get('content-type') || '';
    if (ctype.includes('text/event-stream') && resp.body) {
      await consumeSSE(resp, assistant);
    } else {
      const data = await resp.json();
      finalizeAssistant(assistant, data);
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      assistant.pending = false;
      assistant.content = '请求失败，请稍后重试。';
      assistant.payload = {
        answer_markdown: assistant.content,
        answer_paragraphs: [assistant.content],
        sources: [], figures: [], attached_references: [], reference_links: {}, graph_triples: [],
      };
      state.lastPayload = assistant.payload;
      renderChat();
    }
  } finally {
    state.isSubmitting = false;
    els.askBtn.disabled = false;
    persistChatState();
    if (state.user) await loadConversations();
    else renderHistory();
  }
}

async function consumeSSE(resp, assistant) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let answer = '';
  const answerEl = () => els.chatLog.querySelector('.message.assistant:last-of-type .answer');
  const msgEl = () => els.chatLog.querySelector('.message.assistant:last-of-type');

  const paintStatus = () => {
    if (!assistant.pending) return;
    const el = msgEl();
    if (!el) return;
    // Re-render only this pending bubble for live status steps.
    const idx = Number(el.dataset.msgIdx);
    if (Number.isFinite(idx)) {
      el.outerHTML = renderMessage(assistant, idx);
      els.chatLog.scrollTop = els.chatLog.scrollHeight;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const line = part.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      let event;
      try { event = JSON.parse(line.slice(6)); } catch { continue; }
      if (event.type === 'status') {
        if (!Array.isArray(assistant.statusSteps)) assistant.statusSteps = [];
        assistant.statusSteps.push({
          stage: event.stage || '',
          label: event.label || event.stage || '处理中…',
          detail: event.detail || {},
        });
        paintStatus();
      } else if (event.type === 'token') {
        answer += event.text || '';
        assistant.content = answer;
        assistant.pending = false;
        const el = answerEl();
        if (el) el.innerHTML = decorateCitations(renderMarkdown(answer), state.lastPayload || {});
        else renderChat();
        els.chatLog.scrollTop = els.chatLog.scrollHeight;
      } else if (event.type === 'final') {
        finalizeAssistant(assistant, event.payload || {});
        return;
      }
    }
  }
}

function finalizeAssistant(assistant, payload) {
  assistant.pending = false;
  assistant.payload = payload;
  assistant.content = payload.answer_markdown || assistant.content || '';
  assistant.id = payload.assistant_message_id || assistant.id;
  if (payload.conversation_id) {
    if (state.user) {
      state.activeConversationId = payload.conversation_id;
    } else if (!isLocalConversationId(state.activeConversationId)) {
      // Guests keep local-* ids; ignore server ids if any.
      state.activeConversationId = state.activeConversationId || newLocalConversationId();
    }
  }
  state.lastPayload = payload;
  persistChatState();
  renderChat();
}

function openToolsDrawer(kind) {
  const payload = state.lastPayload;
  if (!payload) { alert('请先完成一次问答'); return; }
  const overlay = document.createElement('div');
  overlay.className = 'drawer-overlay';
  let body = '';
  if (kind === 'trace') {
    body = `<pre style="white-space:pre-wrap;font-size:12px">${escapeHtml(JSON.stringify(payload.trace || {}, null, 2))}</pre>`;
  } else if (kind === 'sources') {
    body = (payload.sources || []).map((s, i) => `
      <div class="evidence-card"><strong>[S${i + 1}] ${escapeHtml(s.printed_page_code || s.source_id)}</strong>
      <div class="muted small">${escapeHtml(s.page_type || '')} · ${escapeHtml(s.section || '')}</div>
      <div style="margin-top:8px">${escapeHtml((s.text || '').slice(0, 400))}</div></div>`).join('') || '<div class="muted">无证据</div>';
  } else if (kind === 'graph') {
    body = (payload.graph_triples || []).map((g, i) => `
      <div class="evidence-card"><strong>[G${i + 1}]</strong> ${escapeHtml(g.subject_name)} → ${escapeHtml(g.relation)} → ${escapeHtml(g.object_name)}
      <div class="muted small">confidence ${Number(g.confidence || 0).toFixed(2)}</div></div>`).join('') || '<div class="muted">无图谱</div>';
  } else {
    body = (payload.figures || []).map((f, i) => renderFigureCard(f, `tool-${i}`)).join('') || '<div class="muted">无流程图</div>';
  }
  overlay.innerHTML = `
    <div class="drawer-panel">
      <div class="drawer-header"><strong>${escapeHtml(kind)}</strong><button class="btn" id="closeToolsDrawer">关闭</button></div>
      <div class="drawer-content">${body}</div>
    </div>`;
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
  document.getElementById('closeToolsDrawer')?.addEventListener('click', () => overlay.remove());
  overlay.querySelectorAll('[data-fig-open]').forEach((el) => {
    el.addEventListener('click', () => openLightbox(el.getAttribute('data-fig-open'), ''));
  });
}

// —— events ——
els.collapseSidebarBtn?.addEventListener('click', () => setSidebarCollapsed(true));
els.expandSidebarBtn?.addEventListener('click', () => setSidebarCollapsed(false));
els.sidebarBackdrop?.addEventListener('click', () => setSidebarCollapsed(true, { persist: false }));
els.newChatBtn?.addEventListener('click', () => newChat());
els.loginOpenBtn?.addEventListener('click', () => openAuthModal('login'));
els.authCloseBtn?.addEventListener('click', closeAuthModal);
// Only close when both press and release happen on the dimmed overlay
// (avoids closing when selecting text then releasing outside the card).
els.authModal?.addEventListener('mousedown', (e) => {
  state.authOverlayDown = e.target === els.authModal;
});
els.authModal?.addEventListener('mouseup', (e) => {
  if (state.authOverlayDown && e.target === els.authModal) closeAuthModal();
  state.authOverlayDown = false;
});
els.authToggleModeBtn?.addEventListener('click', () => {
  openAuthModal(state.authMode === 'login' ? 'register' : 'login');
});
els.authForgotBtn?.addEventListener('click', () => openAuthModal('reset'));
bindPasswordToggle(els.authPwToggle, els.authPassword);
bindPasswordToggle(els.authNewPwToggle, els.authNewPassword);
els.expandInputBtn?.addEventListener('click', () => {
  setComposerExpanded(!state.composerExpanded);
  els.followUpInput?.focus();
});
els.followUpInput?.addEventListener('input', () => resizeComposer());
els.authForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  showAuthError('');
  const email = els.authEmail.value.trim();
  try {
    if (state.authMode === 'reset') {
      const newPassword = els.authNewPassword?.value || '';
      const resp = await api('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ email, new_password: newPassword }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        showAuthError(formatApiDetail(data));
        return;
      }
      setAuthHint(data.message || '密码已更新，请登录。');
      openAuthModal('login');
      setAuthHint(data.message || '密码已更新，请使用新密码登录。');
      return;
    }
    const body = { email, password: els.authPassword.value };
    const path = state.authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    const resp = await api(path, { method: 'POST', body: JSON.stringify(body) });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      showAuthError(formatApiDetail(data));
      return;
    }
    state.user = data;
    detachLocalActiveConversation();
    closeAuthModal();
    renderUserArea();
    await loadConversations();
    await restoreChatAfterLoad();
  } catch {
    showAuthError('网络错误');
  }
});

els.askBtn?.addEventListener('click', () => askQuestion(els.followUpInput.value));
els.followUpInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    askQuestion(els.followUpInput.value);
  }
});

els.toolsBtn?.addEventListener('click', (e) => {
  e.stopPropagation();
  els.toolsMenu.hidden = !els.toolsMenu.hidden;
});
document.addEventListener('click', () => { els.toolsMenu.hidden = true; });
els.toolsMenu?.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-tool]');
  if (!btn) return;
  els.toolsMenu.hidden = true;
  openToolsDrawer(btn.dataset.tool);
});

if (els.shareChatBtn) {
  els.shareChatBtn.innerHTML = ICON.shareChat;
  els.shareChatBtn.addEventListener('click', async () => {
    const url = await createShareLink();
    if (!url) return;
    await copyShareLink(url, els.shareChatBtn, ICON.shareChat, '分享聊天');
  });
}

if (isMobileLayout()) {
  setSidebarCollapsed(true, { persist: false });
} else {
  setSidebarCollapsed(state.sidebarCollapsed);
}
mobileMQ.addEventListener('change', (e) => {
  if (e.matches) {
    setSidebarCollapsed(true, { persist: false });
  } else {
    setSidebarCollapsed(localStorage.getItem('gf_sidebar_collapsed') === '1');
    if (els.sidebarBackdrop) els.sidebarBackdrop.hidden = true;
  }
});
setComposerExpanded(false);
renderChat();
refreshMe();
