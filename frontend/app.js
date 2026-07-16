/* Guideflow frontend (two-column + auth + true SSE). */
const API_BASE = window.API_BASE || 'http://127.0.0.1:8001';

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
  composerBox: document.getElementById('composerBox'),
  expandInputBtn: document.getElementById('expandInputBtn'),
};

const ICON = {
  copy: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>`,
  regen: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>`,
  up: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 11v10"/><path d="M15 21H9a2 2 0 0 1-2-2v-7l5.2-8.1a1.6 1.6 0 0 1 2.9 1.2L14 10h5.4a2 2 0 0 1 1.9 2.6l-1.5 6A2 2 0 0 1 17.9 21H15z"/></svg>`,
  down: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 13V3"/><path d="M9 3h6a2 2 0 0 1 2 2v7l-5.2 8.1a1.6 1.6 0 0 1-2.9-1.2L10 14H4.6a2 2 0 0 1-1.9-2.6l1.5-6A2 2 0 0 1 6.1 3H9z"/></svg>`,
  share: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="M8.4 13.3l7.2 4.4M15.6 6.3l-7.2 4.4"/></svg>`,
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
  sidebarCollapsed: localStorage.getItem('gf_sidebar_collapsed') === '1',
  abortController: null,
};

const ACTIVE_CONV_KEY = 'gf_active_conversation_id';
const DRAFT_KEY = 'gf_chat_draft';
const ICON_EYE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/></svg>`;
const ICON_EYE_OFF = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 10.6a2.5 2.5 0 0 0 3.5 3.5"/><path d="M9.9 5.2A11.3 11.3 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-4.1 4.8"/><path d="M6.1 6.1C3.9 7.8 2 12 2 12s3.5 6 10 6c1.3 0 2.5-.2 3.6-.6"/></svg>`;

function persistChatState() {
  try {
    if (state.activeConversationId) {
      localStorage.setItem(ACTIVE_CONV_KEY, state.activeConversationId);
    } else {
      localStorage.removeItem(ACTIVE_CONV_KEY);
    }
    const draft = {
      conversationId: state.activeConversationId,
      messages: state.messages
        .filter((m) => !m.pending)
        .map((m) => ({
          id: m.id || null,
          role: m.role,
          content: m.content,
          payload: m.payload || null,
          feedback: m.feedback || null,
        })),
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
  if (state.user && savedId) {
    const exists = state.conversations.some((c) => c.id === savedId);
    if (exists) {
      await openConversation(savedId);
      return;
    }
    localStorage.removeItem(ACTIVE_CONV_KEY);
  }
  const draft = loadDraft();
  if (!draft?.messages?.length) return;
  if (draft.conversationId && state.user) {
    const exists = state.conversations.some((c) => c.id === draft.conversationId);
    if (exists) {
      await openConversation(draft.conversationId);
      return;
    }
  }
  state.activeConversationId = draft.conversationId || null;
  state.messages = draft.messages;
  state.lastPayload = draft.lastPayload || null;
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
  if (state.user) await loadConversations();
  else {
    state.conversations = [];
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
      await api('/api/auth/logout', { method: 'POST', body: '{}' });
      state.user = null;
      state.conversations = [];
      state.activeConversationId = null;
      state.messages = [];
      state.lastPayload = null;
      localStorage.removeItem(ACTIVE_CONV_KEY);
      sessionStorage.removeItem(DRAFT_KEY);
      renderUserArea();
      renderHistory();
      renderChat();
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
      els.historyList.innerHTML = `<div class="muted small" style="padding:10px">登录已失效，请重新登录</div>`;
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

function renderHistory() {
  if (!state.user) {
    els.historyList.innerHTML = `<div class="muted small" style="padding:10px">登录后可同步历史记录</div>`;
    return;
  }
  if (!state.conversations.length) {
    els.historyList.innerHTML = `<div class="muted small" style="padding:10px">暂无历史对话</div>`;
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
    await api(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title: title.trim() }) });
    await loadConversations();
  };
  menu.querySelector('[data-act="delete"]').onclick = async () => {
    if (!confirm('确认删除该对话？')) return;
    await api(`/api/conversations/${id}`, { method: 'DELETE' });
    if (state.activeConversationId === id) newChat();
    await loadConversations();
  };
}

async function openConversation(id) {
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

function newChat() {
  state.activeConversationId = null;
  state.messages = [];
  state.lastPayload = null;
  if (state.abortController) state.abortController.abort();
  localStorage.removeItem(ACTIVE_CONV_KEY);
  sessionStorage.removeItem(DRAFT_KEY);
  renderHistory();
  renderChat();
  closeSidebarOnMobile();
  els.followUpInput.focus();
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
    return;
  }
  els.chatLog.innerHTML = state.messages.map((m, idx) => renderMessage(m, idx)).join('');
  bindMessageActions();
  bindCitations();
  bindFigures();
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function renderMessage(message, idx) {
  if (message.role === 'user') {
    return `<div class="message user"><div class="tag">用户提问</div><div>${escapeHtml(message.content)}</div></div>`;
  }
  if (message.pending) {
    return `
      <div class="message assistant" data-msg-idx="${idx}">
        <div class="tag">AI 回答 · 证据约束</div>
        <div class="answer">
          <div class="typing-indicator"><span class="spinner" aria-hidden="true"></span>正在检索与生成回答…</div>
        </div>
      </div>`;
  }
  const payload = message.payload || state.lastPayload || {};
  const body = renderAnswerBody(payload, message.content);
  const feedback = message.feedback || '';
  return `
    <div class="message assistant" data-msg-idx="${idx}" data-msg-id="${escapeHtml(message.id || '')}">
      <div class="tag">AI 回答 · 证据约束</div>
      <div class="answer">${body}</div>
      <div class="msg-actions">
        <button type="button" data-act="copy" title="复制" aria-label="复制">${ICON.copy}</button>
        <button type="button" data-act="regen" title="重说" aria-label="重说">${ICON.regen}</button>
        <button type="button" data-act="up" class="${feedback === 'up' ? 'active' : ''}" title="点赞" aria-label="点赞">${ICON.up}</button>
        <button type="button" data-act="down" class="${feedback === 'down' ? 'active' : ''}" title="点踩" aria-label="点踩">${ICON.down}</button>
        <button type="button" data-act="share" title="分享" aria-label="分享">${ICON.share}</button>
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
    <details class="refs-block" open>
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
  const scheduleHide = () => {
    clearHide();
    state.citeHideTimer = setTimeout(() => {
      pop.hidden = true;
      state.citeHideTimer = null;
    }, 160);
  };
  const scrollToRefs = () => {
    clearHide();
    pop.hidden = true;
    document.querySelector('.refs-block')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const showFor = (btn) => {
    clearHide();
    const type = btn.dataset.cite;
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
  }

  els.chatLog.querySelectorAll('.cite').forEach((btn) => {
    btn.addEventListener('mouseenter', () => showFor(btn));
    btn.addEventListener('mouseleave', scheduleHide);
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      if (pop.hidden) showFor(btn);
      else scrollToRefs();
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
          await navigator.clipboard.writeText(text);
          flashActionIcon(btn, 'check', '已复制', ICON.copy, '复制', 1000);
        } else if (act === 'regen') {
          const userMsg = [...state.messages].slice(0, idx).reverse().find((m) => m.role === 'user');
          if (userMsg) askQuestion(userMsg.content, { regenerate: true });
        } else if (act === 'up' || act === 'down') {
          if (!state.user) { openAuthModal('login'); return; }
          if (!msg.id) { alert('请先登录并完成一次问答以保存消息'); return; }
          const value = msg.feedback === act ? null : act;
          const resp = await api(`/api/messages/${msg.id}/feedback`, {
            method: 'POST',
            body: JSON.stringify({ value }),
          });
          if (resp.ok) {
            msg.feedback = value;
            renderChat();
          }
        } else if (act === 'share') {
          if (!state.user) { openAuthModal('login'); return; }
          let convId = state.activeConversationId;
          if (!convId) {
            alert('当前对话尚未保存到云端。请确认已登录，并在登录后重新提问一次，再分享。');
            return;
          }
          const resp = await api(`/api/conversations/${convId}/share`, { method: 'POST', body: '{}' });
          if (resp.status === 401) {
            state.user = null;
            renderUserArea();
            openAuthModal('login');
            return;
          }
          if (!resp.ok) { alert('分享失败'); return; }
          const data = await resp.json();
          const url = `${location.origin}${location.pathname.replace(/index\.html.?$/, '')}share.html?token=${encodeURIComponent(data.token)}&api=${encodeURIComponent(API_BASE)}`;
          await navigator.clipboard.writeText(url);
          flashActionIcon(btn, 'check', '已复制链接', ICON.share, '分享', 1200);
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

  if (!meta.regenerate) {
    state.messages.push({ role: 'user', content: q });
  } else {
    // Drop trailing assistant message when regenerating.
    if (state.messages.at(-1)?.role === 'assistant') state.messages.pop();
  }
  const assistant = { role: 'assistant', content: '', payload: null, feedback: null, pending: true };
  state.messages.push(assistant);
  renderChat();

  if (state.abortController) state.abortController.abort();
  state.abortController = new AbortController();

  try {
    const resp = await api('/api/ask', {
      method: 'POST',
      body: JSON.stringify({
        question: q,
        stream: true,
        trace: true,
        conversation_id: state.activeConversationId || null,
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
    els.followUpInput.value = '';
    setComposerExpanded(false);
    persistChatState();
    if (state.user) await loadConversations();
  }
}

async function consumeSSE(resp, assistant) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let answer = '';
  const answerEl = () => els.chatLog.querySelector('.message.assistant:last-of-type .answer');

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
      if (event.type === 'token') {
        answer += event.text || '';
        assistant.content = answer;
        assistant.pending = false;
        const el = answerEl();
        if (el) el.innerHTML = decorateCitations(renderMarkdown(answer), state.lastPayload || {});
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
  if (payload.conversation_id) state.activeConversationId = payload.conversation_id;
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
