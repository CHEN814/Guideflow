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
  dataSourceSelect: document.getElementById('dataSourceSelect'),
};

const ICON = {
  copy: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>`,
  regen: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>`,
  up: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 11v10"/><path d="M15 21H9a2 2 0 0 1-2-2v-7l5.2-8.1a1.6 1.6 0 0 1 2.9 1.2L14 10h5.4a2 2 0 0 1 1.9 2.6l-1.5 6A2 2 0 0 1 17.9 21H15z"/></svg>`,
  down: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 13V3"/><path d="M9 3h6a2 2 0 0 1 2 2v7l-5.2 8.1a1.6 1.6 0 0 1-2.9-1.2L10 14H4.6a2 2 0 0 1-1.9-2.6l1.5-6A2 2 0 0 1 6.1 3H9z"/></svg>`,
  share: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="M8.4 13.3l7.2 4.4M15.6 6.3l-7.2 4.4"/></svg>`,
  shareChat: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v10"/><path d="M8 7l4-4 4 4"/><path d="M5 12v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>`,
  check: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 13l4 4L19 7"/></svg>`,
  edit: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>`,
};

const SUGGESTIONS = [
  'DLBCL 一线治疗如何推荐？',
  'DLBCL 中 GCB 与 ABC 有何差异？',
  'TP53 对 DLBCL 预后有何影响？',
  'DLBCL 何时考虑 CNS prophylaxis？',
];

const DATA_SOURCE_KEY = 'gf_data_source';
const DATA_SOURCE_LABELS = { nccn: 'NCCN', csco: 'CSCO' };

function loadDataSource() {
  const v = (localStorage.getItem(DATA_SOURCE_KEY) || 'nccn').toLowerCase();
  return v === 'csco' ? 'csco' : 'nccn';
}

function saveDataSource(key) {
  const v = key === 'csco' ? 'csco' : 'nccn';
  localStorage.setItem(DATA_SOURCE_KEY, v);
  return v;
}

const state = {
  user: null,
  conversations: [],
  activeConversationId: null,
  /** Active path for rendering (derived from tree). */
  messages: [],
  /** Conversation message tree (DeepSeek-style branches). */
  tree: {
    nodesById: {},
    rootIds: [],
    activeRootId: null,
  },
  lastPayload: null,
  isSubmitting: false,
  authMode: 'login', // login | register | reset
  composerExpanded: false,
  authOverlayDown: false,
  citeHideTimer: null,
  citePinned: false,
  sidebarCollapsed: localStorage.getItem('gf_sidebar_collapsed') === '1',
  abortController: null,
  dataSource: loadDataSource(),
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

function newNodeId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `n-${crypto.randomUUID()}`;
  }
  return `n-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function emptyTree() {
  return { nodesById: {}, rootIds: [], activeRootId: null };
}

function resetTree() {
  state.tree = emptyTree();
  state.messages = [];
}

function getNode(id) {
  return id ? state.tree.nodesById[id] || null : null;
}

function createNode({
  role,
  content = '',
  parentId = null,
  serverId = null,
  payload = null,
  feedback = null,
  pending = false,
  id = null,
}) {
  const node = {
    id: id || newNodeId(),
    serverId: serverId || null,
    role,
    content,
    payload,
    feedback,
    parentId,
    childIds: [],
    activeChildId: null,
    pending: Boolean(pending),
    statusSteps: [],
    editing: false,
    citePayload: null,
  };
  state.tree.nodesById[node.id] = node;
  if (parentId) {
    const parent = getNode(parentId);
    if (parent) {
      if (!parent.childIds.includes(node.id)) parent.childIds.push(node.id);
      parent.activeChildId = node.id;
    }
  } else {
    if (!state.tree.rootIds.includes(node.id)) state.tree.rootIds.push(node.id);
    state.tree.activeRootId = node.id;
  }
  return node;
}

function siblingsOf(node) {
  if (!node) return [];
  if (!node.parentId) {
    return state.tree.rootIds.map((id) => getNode(id)).filter(Boolean);
  }
  const parent = getNode(node.parentId);
  if (!parent) return [node];
  return parent.childIds.map((id) => getNode(id)).filter(Boolean);
}

function siblingIndex(node) {
  const sibs = siblingsOf(node);
  return Math.max(0, sibs.findIndex((s) => s.id === node.id));
}

function activeChildOf(node) {
  if (!node) return null;
  if (node.activeChildId && getNode(node.activeChildId)) {
    return getNode(node.activeChildId);
  }
  if (node.childIds.length) {
    return getNode(node.childIds[node.childIds.length - 1]);
  }
  return null;
}

function rebuildActivePath() {
  const path = [];
  let cur = null;
  if (state.tree.activeRootId && getNode(state.tree.activeRootId)) {
    cur = getNode(state.tree.activeRootId);
  } else if (state.tree.rootIds.length) {
    cur = getNode(state.tree.rootIds[state.tree.rootIds.length - 1]);
    state.tree.activeRootId = cur?.id || null;
  }
  const seen = new Set();
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id);
    path.push(cur);
    cur = activeChildOf(cur);
  }
  state.messages = path;
  const lastAsst = [...path].reverse().find((m) => m.role === 'assistant' && !m.pending);
  if (lastAsst?.payload) state.lastPayload = lastAsst.payload;
  return path;
}

function collectSubtreeIds(rootId) {
  const out = [];
  const walk = (id) => {
    const n = getNode(id);
    if (!n) return;
    for (const cid of n.childIds) walk(cid);
    out.push(id);
  };
  walk(rootId);
  return out;
}

function setActiveSibling(node) {
  if (!node) return;
  if (!node.parentId) {
    state.tree.activeRootId = node.id;
  } else {
    const parent = getNode(node.parentId);
    if (parent) parent.activeChildId = node.id;
  }
}

async function syncActiveBranchToServer(node) {
  if (!state.user || !node?.serverId) return;
  const convId = state.activeConversationId;
  if (!convId || isLocalConversationId(convId)) return;
  try {
    const resp = await api(`/api/conversations/${convId}/active-branch`, {
      method: 'POST',
      body: JSON.stringify({ message_id: node.serverId }),
    });
    if (!resp.ok) throw new Error('active-branch failed');
  } catch {
    await openConversation(convId);
  }
}

async function switchBranch(node, delta) {
  const sibs = siblingsOf(node);
  const idx = siblingIndex(node);
  const next = idx + delta;
  if (next < 0 || next >= sibs.length) return;
  setActiveSibling(sibs[next]);
  rebuildActivePath();
  persistChatState();
  renderChat();
  await syncActiveBranchToServer(sibs[next]);
}

async function deleteBranch(node) {
  if (!node) return;
  const sibs = siblingsOf(node);
  const idx = siblingIndex(node);
  const fallback = idx > 0 ? sibs[idx - 1] : (idx + 1 < sibs.length ? sibs[idx + 1] : null);
  const toDelete = collectSubtreeIds(node.id);
  const deleteSet = new Set(toDelete);

  if (node.serverId && state.user && state.activeConversationId
      && !isLocalConversationId(state.activeConversationId)) {
    try {
      const resp = await api(`/api/messages/${node.serverId}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error('delete failed');
    } catch {
      await openConversation(state.activeConversationId);
      return;
    }
  }

  if (!node.parentId) {
    state.tree.rootIds = state.tree.rootIds.filter((id) => !deleteSet.has(id));
    if (state.tree.activeRootId === node.id || deleteSet.has(state.tree.activeRootId)) {
      state.tree.activeRootId = fallback?.id || state.tree.rootIds[0] || null;
    }
  } else {
    const parent = getNode(node.parentId);
    if (parent) {
      parent.childIds = parent.childIds.filter((id) => !deleteSet.has(id));
      if (parent.activeChildId === node.id || deleteSet.has(parent.activeChildId)) {
        parent.activeChildId = fallback?.id || parent.childIds[parent.childIds.length - 1] || null;
      }
    }
  }
  for (const id of Object.keys(state.tree.nodesById)) {
    const n = state.tree.nodesById[id];
    if (deleteSet.has(n.activeChildId)) n.activeChildId = null;
  }
  for (const id of toDelete) delete state.tree.nodesById[id];

  rebuildActivePath();
  persistChatState();
  renderChat();
  if (state.user) await loadConversations();
  else renderHistory();
}

/**
 * Build tree from server messages (with parent_id) or legacy linear / old variant drafts.
 */
function buildTreeFromMessages(list, activeRootId = null) {
  resetTree();
  const raw = Array.isArray(list) ? list : [];
  if (!raw.length) {
    rebuildActivePath();
    return;
  }

  // Tree format: nodes with parentId / parent_id (server always sends parent_id after migration)
  const looksLikeTree = raw.some((m) => (
    Object.prototype.hasOwnProperty.call(m, 'parent_id')
    || Object.prototype.hasOwnProperty.call(m, 'parentId')
    || (Array.isArray(m.childIds) && m.childIds.length)
  ));
  if (looksLikeTree) {
    const idMap = {}; // server/local id -> local node id
    for (const m of raw) {
      const srcId = m.id || m.serverId || newNodeId();
      const node = {
        id: srcId,
        serverId: m.serverId || m.id || null,
        role: m.role,
        content: m.content || '',
        payload: m.payload || null,
        feedback: m.feedback || null,
        parentId: null, // wired in second pass
        childIds: [],
        activeChildId: null,
        pending: false,
        statusSteps: [],
        editing: false,
        citePayload: null,
        _rawParent: m.parent_id ?? m.parentId ?? null,
        _rawActiveChild: m.active_child_id ?? m.activeChildId ?? null,
      };
      state.tree.nodesById[node.id] = node;
      idMap[srcId] = node.id;
      if (m.serverId && m.serverId !== srcId) idMap[m.serverId] = node.id;
    }
    for (const node of Object.values(state.tree.nodesById)) {
      const pid = node._rawParent;
      if (pid && idMap[pid]) {
        node.parentId = idMap[pid];
        const parent = getNode(node.parentId);
        if (parent && !parent.childIds.includes(node.id)) parent.childIds.push(node.id);
      } else {
        if (!state.tree.rootIds.includes(node.id)) state.tree.rootIds.push(node.id);
      }
      delete node._rawParent;
    }
    // Preserve creation order in childIds / rootIds by original list order
    state.tree.rootIds = raw
      .filter((m) => !(m.parent_id ?? m.parentId))
      .map((m) => idMap[m.id || m.serverId])
      .filter(Boolean);
    for (const node of Object.values(state.tree.nodesById)) {
      const kids = raw
        .filter((m) => (m.parent_id ?? m.parentId) === (node.serverId || node.id)
          || (m.parent_id ?? m.parentId) === node.id)
        .map((m) => idMap[m.id || m.serverId])
        .filter(Boolean);
      if (kids.length) node.childIds = kids;
    }
    for (const node of Object.values(state.tree.nodesById)) {
      const ac = node._rawActiveChild;
      if (ac && idMap[ac]) node.activeChildId = idMap[ac];
      else if (node.childIds.length) node.activeChildId = node.childIds[node.childIds.length - 1];
      delete node._rawActiveChild;
    }
    if (activeRootId && idMap[activeRootId]) state.tree.activeRootId = idMap[activeRootId];
    else if (state.tree.rootIds.length) {
      state.tree.activeRootId = state.tree.rootIds[state.tree.rootIds.length - 1];
    }
    rebuildActivePath();
    return;
  }

  // Legacy flat list (ignore old variants — keep linear active path only)
  let prevId = null;
  for (const m of raw) {
    if (m.pending) continue;
    const node = createNode({
      role: m.role,
      content: m.content || '',
      parentId: prevId,
      serverId: m.id || m.serverId || null,
      payload: m.payload || null,
      feedback: m.feedback || null,
      id: m.id || undefined,
    });
    // createNode already appends; for linear chain fix roots when not first
    if (prevId) {
      state.tree.rootIds = state.tree.rootIds.filter((id) => id !== node.id);
      state.tree.activeRootId = state.tree.rootIds[0] || state.tree.activeRootId;
      const parent = getNode(prevId);
      if (parent) parent.activeChildId = node.id;
    }
    prevId = node.id;
  }
  if (state.tree.rootIds.length) {
    state.tree.activeRootId = state.tree.rootIds[0];
  }
  rebuildActivePath();
}

function snapshotTreeForStore() {
  const nodes = Object.values(state.tree.nodesById).filter((n) => !n.pending);
  return {
    activeRootId: state.tree.activeRootId,
    messages: nodes.map((n) => ({
      id: n.id,
      serverId: n.serverId,
      role: n.role,
      content: n.content,
      payload: n.payload || null,
      feedback: n.feedback || null,
      parentId: n.parentId,
      activeChildId: n.activeChildId,
      childIds: n.childIds.slice(),
    })),
  };
}

function conversationTitleFromMessages(messages) {
  const firstUser = (messages || []).find((m) => m.role === 'user' && m.content);
  const raw = String(firstUser?.content || '新对话').trim().replace(/\s+/g, ' ');
  return (raw.slice(0, 40) || '新对话');
}

function conversationTitleFromTree() {
  const root = getNode(state.tree.activeRootId) || getNode(state.tree.rootIds[0]);
  const raw = String(root?.content || '新对话').trim().replace(/\s+/g, ' ');
  return (raw.slice(0, 40) || '新对话');
}

function localConversationsAsSummaries(list) {
  return (list || []).map((c) => ({
    id: c.id,
    title: c.title || '新对话',
    updated_at: c.updated_at,
    created_at: c.updated_at,
    message_count: c.tree?.messages?.length
      ?? (c.messages || []).length,
  }));
}

function syncLocalConversationsToState() {
  const list = loadLocalConversations();
  list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  state.conversations = localConversationsAsSummaries(list);
}

function upsertLocalConversationFromState() {
  if (state.user) return;
  const snap = snapshotTreeForStore();
  if (!snap.messages.length) return;

  let id = state.activeConversationId;
  if (!isLocalConversationId(id)) {
    id = newLocalConversationId();
    state.activeConversationId = id;
  }

  const list = loadLocalConversations();
  const prev = list.find((c) => c.id === id);
  const autoTitle = conversationTitleFromTree();
  const prevAuto = prev?.tree
    ? (String(prev.tree.messages?.find((m) => m.role === 'user')?.content || '新对话').trim().slice(0, 40) || '新对话')
    : conversationTitleFromMessages(prev?.messages || []);
  const keepRename = Boolean(prev?.title && prev.title !== '新对话' && prev.title !== prevAuto);
  const entry = {
    id,
    title: keepRename ? prev.title : autoTitle,
    updated_at: new Date().toISOString(),
    tree: snap,
    // Keep flat messages for older readers (active path only)
    messages: state.messages.filter((m) => !m.pending).map((m) => ({
      id: m.id,
      serverId: m.serverId,
      role: m.role,
      content: m.content,
      payload: m.payload || null,
      feedback: m.feedback || null,
      parentId: m.parentId,
      activeChildId: m.activeChildId,
    })),
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
  if (conv.tree?.messages?.length) {
    buildTreeFromMessages(conv.tree.messages, conv.tree.activeRootId);
  } else {
    buildTreeFromMessages(conv.messages || [], null);
  }
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
    const snap = snapshotTreeForStore();
    const draft = {
      conversationId: state.activeConversationId,
      tree: snap,
      messages: snap.messages,
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
  const draftMsgs = draft?.tree?.messages || draft?.messages;
  if (!draftMsgs?.length) {
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
  buildTreeFromMessages(draftMsgs, draft.tree?.activeRootId || draft.activeRootId || null);
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

function normalizeMarkdownRanges(md) {
  // CSCO / clinical Chinese uses ASCII "~" for numeric ranges (IPI 2~5, 40~50mg,
  // d1~5). GFM strikethrough is "~~…~~"; a pair of single "~" in one paragraph
  // can still be mis-parsed as <del> by some marked builds. Normalize ranges to
  // the fullwidth tilde so they never become strikethrough.
  return String(md || '').replace(
    /([0-9A-Za-z])\s*~\s*([0-9A-Za-z])/g,
    '$1～$2',
  );
}

function renderMarkdown(md) {
  const raw = normalizeMarkdownRanges(md);
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
  buildTreeFromMessages(data.messages || [], data.active_root_id || null);
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
  resetTree();
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
  bindTables();
  updateShareChatBtn();
  const editingInput = els.chatLog.querySelector('.user-edit-input');
  if (editingInput) {
    editingInput.focus();
    editingInput.setSelectionRange(editingInput.value.length, editingInput.value.length);
    editingInput.closest('.message')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } else {
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }
}

function renderVersionNav(current, total, prevAct, nextAct) {
  if (total <= 1) return '';
  return `
    <span class="msg-version">
      <button type="button" data-act="${prevAct}" ${current <= 0 ? 'disabled' : ''} title="上一版本" aria-label="上一版本">‹</button>
      <span class="msg-version-label">${current + 1} / ${total}</span>
      <button type="button" data-act="${nextAct}" ${current >= total - 1 ? 'disabled' : ''} title="下一版本" aria-label="下一版本">›</button>
    </span>`;
}

function renderBranchControls(message) {
  const sibs = siblingsOf(message);
  const total = sibs.length;
  const current = siblingIndex(message);
  const vNav = renderVersionNav(current, total, 'prev-branch', 'next-branch');
  // Always show delete on both sides (remove this node + its subtree).
  const delBtn = `<button type="button" data-act="del-branch" class="btn-del-branch" title="删除此分支" aria-label="删除此分支"${state.isSubmitting ? ' disabled' : ''}>${ICON.trash}</button>`;
  return { vNav, delBtn, total };
}

function renderMessage(message, idx) {
  if (message.role === 'user') {
    if (message.editing) {
      return `
        <div class="msg-row user editing" data-msg-idx="${idx}" data-node-id="${escapeHtml(message.id || '')}">
          <div class="message user editing">
            <div class="user-edit-box">
              <textarea class="user-edit-input" rows="3" aria-label="编辑问题">${escapeHtml(message.content)}</textarea>
              <div class="user-edit-actions">
                <button type="button" class="btn ghost" data-act="edit-cancel">取消</button>
                <button type="button" class="btn primary" data-act="edit-send">发送</button>
              </div>
            </div>
          </div>
        </div>`;
    }
    const { vNav, delBtn } = renderBranchControls(message);
    return `
      <div class="msg-row user" data-msg-idx="${idx}" data-node-id="${escapeHtml(message.id || '')}">
        <div class="message user">
          <div class="tag">用户提问</div>
          <div class="user-content">${escapeHtml(message.content)}</div>
        </div>
        <div class="msg-actions msg-actions-user">
          ${vNav}
          <span class="msg-actions-icons">
            ${delBtn}
            <button type="button" data-act="copy-user" title="复制" aria-label="复制">${ICON.copy}</button>
            <button type="button" data-act="edit" title="编辑" aria-label="编辑"${state.isSubmitting ? ' disabled' : ''}>${ICON.edit}</button>
          </span>
        </div>
      </div>`;
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
      <div class="msg-row assistant" data-msg-idx="${idx}" data-node-id="${escapeHtml(message.id || '')}">
        <div class="message assistant">
          <div class="tag">AI 回答</div>
          <div class="answer">
            <div class="typing-indicator">
              <span class="spinner" aria-hidden="true"></span>
              <span class="status-current">${escapeHtml(current)}</span>
            </div>
            ${stepsHtml}
          </div>
        </div>
      </div>`;
  }
  const payload = message.payload || state.lastPayload || {};
  const body = renderAnswerBody(payload, message.content);
  const feedback = message.feedback || '';
  const tag = answerKindLabel(payload.answer_kind);
  const src = (payload.data_source || message.dataSource || '').toLowerCase();
  const srcChip = src
    ? `<span class="source-chip ${src === 'csco' ? 'csco' : ''}">${escapeHtml(DATA_SOURCE_LABELS[src] || src)}</span>`
    : '';
  const { vNav, delBtn } = renderBranchControls(message);
  return `
    <div class="msg-row assistant" data-msg-idx="${idx}" data-node-id="${escapeHtml(message.id || '')}" data-msg-id="${escapeHtml(message.serverId || message.id || '')}">
      <div class="message assistant">
        <div class="tag">${escapeHtml(tag)}${srcChip}</div>
        <div class="answer">${body}</div>
      </div>
      <div class="msg-actions">
        ${vNav}
        <span class="msg-actions-icons">
          ${delBtn}
          <button type="button" data-act="copy" title="复制" aria-label="复制">${ICON.copy}</button>
          <button type="button" data-act="regen" title="重说" aria-label="重说"${state.isSubmitting ? ' disabled' : ''}>${ICON.regen}</button>
          <button type="button" data-act="up" class="${feedback === 'up' ? 'active' : ''}" title="点赞" aria-label="点赞">${ICON.up}</button>
          <button type="button" data-act="down" class="${feedback === 'down' ? 'active' : ''}" title="点踩" aria-label="点踩">${ICON.down}</button>
          <button type="button" data-act="share" title="分享此回答" aria-label="分享此回答">${ICON.share}</button>
        </span>
      </div>
    </div>`;
}

function isTableSource(s) {
  return !!s && (s.is_table === true || s.content_type === 'table') && !!(s.table_markdown || s.text);
}

// Map each cited table source to the paragraph that first references it, so the
// full table renders inline (not hidden inside an evidence card). Returns the
// per-paragraph table indices plus any cited tables left unanchored.
function planCitedTables(paragraphs, payload) {
  const sources = payload.sources || [];
  const byParagraph = paragraphs.map(() => []);
  const placed = new Set();
  paragraphs.forEach((p, idx) => {
    const re = /\[S(\d+)\]/gi;
    let m;
    while ((m = re.exec(String(p))) !== null) {
      const si = Number(m[1]) - 1;
      if (placed.has(si)) continue;
      if (isTableSource(sources[si])) {
        placed.add(si);
        byParagraph[idx].push(si);
      }
    }
  });
  // Table evidence that exists but was never cited → still show it to the reader.
  const leftovers = [];
  sources.forEach((s, si) => {
    if (isTableSource(s) && !placed.has(si)) leftovers.push(si);
  });
  return { byParagraph, leftovers };
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
  const sources = payload.sources || [];
  const tablePlan = planCitedTables(paragraphs, payload);
  let html = paragraphs.map((p, idx) => {
    const figs = (anchored.get(idx) || []).map((f, i) => renderFigureCard(f, `${idx}-${i}`)).join('');
    const tbls = tablePlan.byParagraph[idx]
      .map((si) => renderTableCard(sources[si], si))
      .join('');
    return `<div class="answer-block">${decorateCitations(renderMarkdown(p), payload)}${tbls}${figs}</div>`;
  }).join('');
  if (tablePlan.leftovers.length) {
    html += `<div class="answer-block table-extra">${tablePlan.leftovers.map((si) => renderTableCard(sources[si], si)).join('')}</div>`;
  }
  if (unanchored.length) {
    html += `<div class="answer-block"><h3>相关流程图</h3>${unanchored.map((f, i) => renderFigureCard(f, `u-${i}`)).join('')}</div>`;
  }
  html += `<p class="ai-disclaimer">本回答由 AI 生成，内容仅供参考，请仔细甄别</p>`;
  html += renderReferences(payload);
  return html;
}

function renderTableCard(s, key) {
  if (!s) return '';
  const md = String(s.table_markdown || s.text || '').trim();
  if (!md) return '';
  let caption = s.display_title || s.citation_label || '指南表格';
  let bodyMd = md;
  const capMatch = md.match(/^\*\*(.+?)\*\*\s*\n+/);
  if (capMatch) {
    caption = capMatch[1].trim();
    bodyMd = md.slice(capMatch[0].length).trim();
  }
  const tableHtml = renderMarkdown(bodyMd);
  const foot = [s.citation_label, s.source_label].filter(Boolean).join(' · ');
  const copyPayload = encodeURIComponent(bodyMd);
  return `
    <figure class="table-card" data-table-key="${escapeHtml(String(key))}">
      <figcaption class="table-card-head">
        <span class="table-card-title">${escapeHtml(caption)}</span>
        <button type="button" class="table-copy" data-copy-md="${copyPayload}" title="复制表格" aria-label="复制表格">${ICON.copy}<span class="table-copy-label">复制</span></button>
      </figcaption>
      <div class="table-card-body">${tableHtml}</div>
      ${foot ? `<figcaption class="table-card-foot">${escapeHtml(foot)}</figcaption>` : ''}
    </figure>`;
}

function renderFigureCard(fig, key) {
  const compact = resolveImageUrl(fig.image_url || fig.full_image_url);
  const full = resolveImageUrl(fig.full_image_url || fig.image_url);
  if (!compact) return '';
  const label = fig.page_code || `pdf_page=${fig.pdf_page}`;
  return `
    <figure class="figure-card" data-fig-key="${escapeHtml(key)}">
      <div class="fig-head">
        <span>${escapeHtml(label)}</span>
        <button type="button" class="btn ghost" data-fig-open="${escapeHtml(full || compact)}" data-fig-label="${escapeHtml(label)}">原图</button>
      </div>
      <img src="${escapeHtml(compact)}" alt="${escapeHtml(label)}" data-fig-open="${escapeHtml(full || compact)}" />
      ${fig.caption ? `<div class="fig-cap">${escapeHtml(fig.caption)}</div>` : ''}
    </figure>`;
}

function decorateCitations(html, payload) {
  const sources = payload.sources || [];
  const refs = payload.attached_references || [];
  return html
    .replace(/\[S(\d+)\]/gi, (_, n) => {
      const idx = Number(n) - 1;
      const s = sources[idx] || {};
      const label = s.citation_label || s.printed_page_code || `S${n}`;
      const tip = escapeHtml(s.display_title || label);
      return `<button class="cite" data-cite="S" data-index="${idx}" aria-label="${tip}">${escapeHtml(label)}</button>`;
    })
    .replace(/\[G(\d+)\]/gi, (_, n) => {
      const idx = Number(n) - 1;
      return `<button class="cite" data-cite="G" data-index="${idx}">G${n}</button>`;
    })
    .replace(/(?<!\w)G(\d+)(?!\w)/g, (_, n) => `<button class="cite" data-cite="G" data-index="${Number(n) - 1}">G${n}</button>`)
    .replace(/\[(\d{1,3})\]/g, (m, n) => {
      const hit = refs.find((r) => String(r.ref_number) === String(n));
      if (!hit) return m;
      const label = hit.author_year || hit.citation_label || n;
      const tip = escapeHtml(hit.display_title || label);
      return `<button class="cite" data-cite="R" data-ref="${escapeHtml(String(n))}" aria-label="${tip}">${escapeHtml(label)}</button>`;
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
  const graph = payload.graph_triples || [];
  if (!sources.length && !refs.length && !graph.length) return '';
  const items = [];
  sources.forEach((s, i) => {
    const metaParts = [s.subtitle, s.source_label, s.locator].filter(Boolean);
    items.push({
      title: s.display_title || s.printed_page_code || s.source_id || `Source ${i + 1}`,
      meta: metaParts.join(' · ') || (s.page_type || 'source'),
      badge: s.badge || (s.page_type === 'clinical_guideline' ? '指南' : (s.page_type || 'Source')),
    });
  });
  refs.forEach((r) => {
    items.push({
      title: r.display_title || r.paper_title || (r.text || '').replace(/\s+/g, ' ').trim(),
      meta: r.source_label || [r.journal, r.year, r.authors].filter(Boolean).join('. ') || 'Literature',
      badge: r.badge || '文献',
      url: r.url,
    });
  });
  graph.forEach((g, i) => {
    const sourceTag = g.review_status === 'synthetic' ? 'Synthetic' : (g.evidence_kind === 'neo4j' ? 'Neo4j' : 'Graph');
    items.push({
      title: `${g.subject_name || ''} → ${g.relation || ''} → ${g.object_name || ''}`,
      meta: (g.evidence_text || '').slice(0, 160) || `confidence ${Number(g.confidence || 0).toFixed(2)}`,
      badge: sourceTag,
      cite: { type: 'G', index: i },
    });
  });
  return `
    <details class="refs-block" open>
      <summary>
        <span class="refs-summary-left">
          <svg class="refs-icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <text x="1" y="5" font-size="5" fill="currentColor" font-family="sans-serif">1</text>
            <line x1="7" y1="3.5" x2="15" y2="3.5" stroke="currentColor" stroke-width="1.2"/>
            <text x="1" y="10" font-size="5" fill="currentColor" font-family="sans-serif">2</text>
            <line x1="7" y1="8.5" x2="15" y2="8.5" stroke="currentColor" stroke-width="1.2"/>
            <text x="1" y="15" font-size="5" fill="currentColor" font-family="sans-serif">3</text>
            <line x1="7" y1="13.5" x2="15" y2="13.5" stroke="currentColor" stroke-width="1.2"/>
          </svg>
          <span>References & Graph</span>
        </span>
        <span class="muted small">${items.length}</span>
      </summary>
      ${items.map((it, i) => `
        <div class="ref-item">
          <div class="rtitle"><span class="rnum">${i + 1}.</span> ${it.cite ? `<button class="cite" data-cite="${it.cite.type}" data-index="${it.cite.index}">G${it.cite.index + 1}</button> ` : ''}${it.url ? `<a href="${escapeHtml(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a>` : escapeHtml(it.title)}</div>
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

function bindTables() {
  els.chatLog.querySelectorAll('.table-copy[data-copy-md]').forEach((el) => {
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      const md = decodeURIComponent(el.getAttribute('data-copy-md') || '');
      if (!md) return;
      const label = el.querySelector('.table-copy-label');
      const done = () => {
        el.classList.add('copied');
        const prev = label ? label.textContent : '';
        if (label) label.textContent = '已复制';
        setTimeout(() => {
          el.classList.remove('copied');
          if (label) label.textContent = prev || '复制';
        }, 1400);
      };
      try {
        await navigator.clipboard.writeText(md);
        done();
      } catch {
        const ta = document.createElement('textarea');
        ta.value = md;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch { /* ignore */ }
        ta.remove();
      }
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

function isNoiseLabel(value) {
  const s = String(value || '').trim();
  if (!s) return true;
  if (/^\d+$/.test(s)) return true;
  if (/^\[\d+\]$/.test(s)) return true;
  if (/^\d{5,}$/.test(s)) return true;
  if (/^(node|edge|entity|item|page|triple)[:_\-]?\d*$/i.test(s)) return true;
  return false;
}

function humanizeNodeLabel(node) {
  const props = node?.properties || {};
  const type = String(node?.type || '').toLowerCase();
  if (type.includes('triple')) {
    const subj = String(props.subject_name || '').trim();
    const rel = String(props.relation || '').trim();
    const obj = String(props.object_name || '').trim();
    if (subj && rel && obj) return `${subj} → ${rel} → ${obj}`;
  }
  if (type.includes('reference')) {
    const refNo = props.ref_number != null ? String(props.ref_number) : '';
    const text = String(props.text || props.title || props.name || '').replace(/\s+/g, ' ').trim();
    const snippet = text ? text.slice(0, 42) : '';
    if (refNo && snippet) return `文献${refNo} · ${snippet}`;
    if (snippet) return snippet;
    if (refNo) return `文献 ${refNo}`;
  }
  const candidates = [
    props.name,
    props.title,
    props.label,
    node?.label,
    props.page_code,
    props.printed_page_code,
    props.article_title,
    props.subject_name,
    props.object_name,
    props.source_name,
    props.text ? String(props.text).slice(0, 42) : '',
    node?.id,
  ];
  for (const candidate of candidates) {
    const text = String(candidate || '').trim();
    if (!text || isNoiseLabel(text)) continue;
    return text;
  }
  return '未命名节点';
}

function normalizeConceptKey(label) {
  return String(label || '')
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, '')
    .trim();
}

/** Collapse TrustedTriple intermediates into concept–relation–concept edges (Neo4j Browser style). */
function projectClinicalGraph(data) {
  const rawNodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const rawEdges = Array.isArray(data?.edges) ? data.edges : [];
  const byId = new Map(rawNodes.map((n) => [String(n.id), n]));

  const isTriple = (n) => String(n?.type || '').toLowerCase().includes('triple');
  const isStructuralRel = (rel) => {
    const r = String(rel || '').toUpperCase();
    return r === 'SUBJECT_OF' || r === 'OBJECT_OF' || r === 'EDGE' || r === 'RELATED_TO';
  };

  // Build subject/object of each triple via SUBJECT_OF / OBJECT_OF or triple properties.
  const tripleSubjects = new Map();
  const tripleObjects = new Map();
  for (const e of rawEdges) {
    const rel = String(e.label || e.type || '').toUpperCase();
    const s = String(e.source);
    const t = String(e.target);
    if (rel === 'SUBJECT_OF') tripleSubjects.set(t, s);
    if (rel === 'OBJECT_OF') tripleObjects.set(s, t);
  }

  const conceptNodes = [];
  const idAlias = new Map(); // original id -> merged concept key
  const merged = new Map(); // concept key -> node

  const ensureConcept = (node) => {
    if (!node || isTriple(node)) return null;
    const displayLabel = humanizeNodeLabel(node);
    const key = normalizeConceptKey(displayLabel) || String(node.id);
    if (!merged.has(key)) {
      const item = {
        ...node,
        id: key,
        displayLabel,
        type: String(node.type || 'Concept'),
        properties: { ...(node.properties || {}), original_ids: [String(node.id)] },
      };
      merged.set(key, item);
      conceptNodes.push(item);
    } else {
      const exist = merged.get(key);
      const ids = exist.properties.original_ids || [];
      if (!ids.includes(String(node.id))) ids.push(String(node.id));
      exist.properties.original_ids = ids;
    }
    idAlias.set(String(node.id), key);
    return key;
  };

  for (const n of rawNodes) {
    if (!isTriple(n)) ensureConcept(n);
  }

  const edgeKeySet = new Set();
  const edges = [];
  const pushEdge = (source, target, label) => {
    if (!source || !target || source === target) return;
    const rel = String(label || 'RELATED_TO').toUpperCase();
    if (isStructuralRel(rel)) return;
    const k = `${source}|${rel}|${target}`;
    if (edgeKeySet.has(k)) return;
    edgeKeySet.add(k);
    edges.push({
      id: k,
      source,
      target,
      label: rel,
      type: rel,
      properties: {},
    });
  };

  // Concept edges from triple nodes (preferred clinical relations).
  for (const n of rawNodes) {
    if (!isTriple(n)) continue;
    const props = n.properties || {};
    const tid = String(n.id);
    let subjId = tripleSubjects.get(tid);
    let objId = tripleObjects.get(tid);
    if (!subjId && props.subject_id) subjId = String(props.subject_id);
    if (!objId && props.object_id) objId = String(props.object_id);
    // Also match by name if id missing
    if (!subjId && props.subject_name) {
      const hit = rawNodes.find((x) => !isTriple(x) && humanizeNodeLabel(x) === props.subject_name);
      if (hit) subjId = String(hit.id);
    }
    if (!objId && props.object_name) {
      const hit = rawNodes.find((x) => !isTriple(x) && humanizeNodeLabel(x) === props.object_name);
      if (hit) objId = String(hit.id);
    }
    // Synthesize concept nodes from names if needed
    if (!subjId && props.subject_name) {
      const fake = { id: `name:${props.subject_name}`, label: props.subject_name, type: props.subject_type || 'OntologyConcept', properties: { name: props.subject_name } };
      subjId = ensureConcept(fake) || String(fake.id);
      if (!byId.has(String(fake.id))) byId.set(String(fake.id), fake);
    }
    if (!objId && props.object_name) {
      const fake = { id: `name:${props.object_name}`, label: props.object_name, type: props.object_type || 'OntologyConcept', properties: { name: props.object_name } };
      objId = ensureConcept(fake) || String(fake.id);
      if (!byId.has(String(fake.id))) byId.set(String(fake.id), fake);
    }
    const sKey = subjId ? (idAlias.get(String(subjId)) || ensureConcept(byId.get(String(subjId))) || ensureConcept({ id: subjId, label: props.subject_name, type: 'OntologyConcept', properties: { name: props.subject_name } })) : null;
    const oKey = objId ? (idAlias.get(String(objId)) || ensureConcept(byId.get(String(objId))) || ensureConcept({ id: objId, label: props.object_name, type: 'OntologyConcept', properties: { name: props.object_name } })) : null;
    const rel = props.relation || n.label || 'RELATED_TO';
    pushEdge(sKey, oKey, rel);
  }

  // Direct non-structural edges between concepts
  for (const e of rawEdges) {
    const rel = String(e.label || e.type || '');
    if (isStructuralRel(rel)) continue;
    const sn = byId.get(String(e.source));
    const tn = byId.get(String(e.target));
    if (!sn || !tn || isTriple(sn) || isTriple(tn)) continue;
    const sKey = idAlias.get(String(e.source)) || ensureConcept(sn);
    const tKey = idAlias.get(String(e.target)) || ensureConcept(tn);
    pushEdge(sKey, tKey, rel);
  }

  // Resolve center to merged concept key
  let center = String(data?.center || '');
  if (idAlias.has(center)) center = idAlias.get(center);
  else {
    const cn = byId.get(center);
    if (cn && !isTriple(cn)) {
      const k = ensureConcept(cn);
      if (k) center = k;
    } else {
      const byName = conceptNodes.find((n) => normalizeConceptKey(n.displayLabel) === normalizeConceptKey(center));
      if (byName) center = byName.id;
      else if (conceptNodes[0]) center = conceptNodes[0].id;
    }
  }

  // Prefer connected neighborhood around center (max ~18 nodes)
  const adj = new Map();
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, new Set());
    if (!adj.has(e.target)) adj.set(e.target, new Set());
    adj.get(e.source).add(e.target);
    adj.get(e.target).add(e.source);
  }
  const keep = new Set();
  if (center) {
    keep.add(center);
    const q = [center];
    while (q.length && keep.size < 18) {
      const cur = q.shift();
      for (const nb of adj.get(cur) || []) {
        if (keep.has(nb)) continue;
        keep.add(nb);
        q.push(nb);
        if (keep.size >= 18) break;
      }
    }
  }
  let nodes = conceptNodes.filter((n) => keep.size === 0 || keep.has(n.id));
  if (!nodes.length) nodes = conceptNodes.slice(0, 18);
  const nodeIds = new Set(nodes.map((n) => n.id));
  const finalEdges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));


  const finalNodeIds = new Set(nodes.map((n) => n.id));
  const finalFocusedEdges = finalEdges.filter((e) => finalNodeIds.has(e.source) && finalNodeIds.has(e.target));

  return {
    center,
    depth: data?.depth,
    nodes,
    edges: finalFocusedEdges,
    stats: { nodes: nodes.length, edges: finalFocusedEdges.length },
  };
}

function renderNeo4jGraph(data, selectedId = '') {
  const projected = projectClinicalGraph(data || {});
  const nodes = projected.nodes || [];
  const edges = projected.edges || [];
  if (!nodes.length) return '<div class="muted" style="padding:16px">没有可视化数据（请换一个临床实体 seed，如 DLBCL / TP53 / R-CHOP）</div>';

  const typeWeight = (type) => {
    const t = String(type || '').toLowerCase();
    if (t.includes('disease') || t.includes('diagnos') || t.includes('concept')) return 5;
    if (t.includes('treat') || t.includes('drug') || t.includes('therapy') || t.includes('regimen')) return 4;
    if (t.includes('biomarker') || t.includes('gene') || t.includes('protein') || t.includes('mutation')) return 4;
    if (t.includes('outcome') || t.includes('prognos') || t.includes('risk')) return 3;
    if (t.includes('page') || t.includes('reference')) return 1;
    return 2;
  };
  const scored = nodes.map((n) => {
    const deg = edges.filter((e) => e.source === n.id || e.target === n.id).length;
    const score = typeWeight(n.type) + Math.min(4, deg) + (String(n.id) === String(projected.center) ? 5 : 0);
    return { ...n, __score: score, displayLabel: n.displayLabel || humanizeNodeLabel(n), __focus: false };
  });

  const w = 980;
  const h = 700;
  const cx = w / 2;
  const cy = h / 2;
  const centerNode = scored.find((n) => String(n.id) === String(projected.center)) || scored[0];
  const others = scored.filter((n) => String(n.id) !== String(centerNode?.id));

  // Simple force-ish layout: center + one ring (Neo4j Browser-like star)
  const layout = [];
  if (centerNode) layout.push({ ...centerNode, x: cx, y: cy });
  const n = Math.max(others.length, 1);
  const radius = Math.min(280, 120 + n * 12);
  others.forEach((node, idx) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * idx) / n;
    layout.push({
      ...node,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    });
  });
  // Light repulsion pass
  for (let iter = 0; iter < 40; iter += 1) {
    for (let i = 0; i < layout.length; i += 1) {
      for (let j = i + 1; j < layout.length; j += 1) {
        const a = layout[i];
        const b = layout[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const minD = 88;
        if (dist < minD) {
          const push = (minD - dist) / 2;
          dx /= dist;
          dy /= dist;
          if (i !== 0) {
            a.x -= dx * push;
            a.y -= dy * push;
          }
          if (j !== 0) {
            b.x += dx * push;
            b.y += dy * push;
          }
        }
      }
    }
  }
  if (centerNode) {
    layout[0].x = cx;
    layout[0].y = cy;
  }

  const nodeMap = new Map(layout.map((n) => [String(n.id), n]));
  const edgeLines = edges.map((edge) => {
    const s = nodeMap.get(String(edge.source));
    const t = nodeMap.get(String(edge.target));
    if (!s || !t) return '';
    const midX = (s.x + t.x) / 2;
    const midY = (s.y + t.y) / 2;
    const rawLabel = String(edge.label || edge.type || '').replace(/_/g, ' ');
    const label = escapeHtml(rawLabel.slice(0, 22));
    return `
      <g>
        <line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke="#9aa4b2" stroke-width="1.6" marker-end="url(#arrow)" />
        ${label ? `<rect x="${midX - Math.min(40, label.length * 3)}" y="${midY - 11}" width="${Math.min(90, Math.max(28, label.length * 6))}" height="15" rx="7" fill="rgba(248,250,252,.96)" stroke="rgba(148,163,184,.35)" />` : ''}
        ${label ? `<text x="${midX}" y="${midY}" text-anchor="middle" font-size="9" fill="#64748b">${label}</text>` : ''}
      </g>`;
  }).join('');

  const typeColor = (type) => {
    const t = String(type || '').toLowerCase();
    if (t.includes('disease') || t.includes('diagnos')) return '#4f86f7';
    if (t.includes('treat')) return '#2f9e6a';
    if (t.includes('biomarker') || t.includes('gene') || t.includes('protein')) return '#f59e0b';
    if (t.includes('reference')) return '#94a3b8';
    if (t.includes('concept')) return '#64748b';
    return '#94a3b8';
  };

  const nodeEls = layout.map((node) => {
    const selected = String(node.id) === String(selectedId);
    const isCenter = String(node.id) === String(centerNode?.id);
    const isFocus = Boolean(node.__focus);
    const fill = isCenter ? '#fff7ed' : '#e2e8f0';
    const opacity = 1;
    const labelRaw = String(node.displayLabel || node.label || node.id);
    const label = escapeHtml(labelRaw.length > 18 ? `${labelRaw.slice(0, 16)}…` : labelRaw);
    const tooltip = escapeHtml([
      `名称: ${labelRaw}`,
      `类型: ${String(node.type || '')}`,
      `ID: ${String(node.id || '')}`,
    ].join('\n'));
    const r = isCenter ? 34 : 26;
    return `
      <g class="neo4j-node ${selected ? 'selected' : ''}" data-node-id="${escapeHtml(String(node.id))}" data-node-label="${escapeHtml(labelRaw)}" style="cursor:pointer;opacity:${opacity}">
        <title>${tooltip}</title>
        <circle cx="${node.x}" cy="${node.y}" r="${r}" fill="${fill}" stroke="${selected || isCenter ? '#ea580c' : typeColor(node.type)}" stroke-width="${selected || isCenter ? '3' : '1.6'}" />
        <text x="${node.x}" y="${node.y + 4}" text-anchor="middle" font-size="${isCenter ? 12 : 10}" fill="#1e293b" font-weight="${isCenter ? '600' : '500'}">${label}</text>
      </g>`;
  }).join('');

  return `
    <div class="muted small" style="padding:12px 14px 0">中心：${escapeHtml(String(centerNode?.displayLabel || projected.center || ''))} · 概念节点 ${layout.length} · 关系 ${edges.length}</div>
    <svg viewBox="0 0 ${w} ${h}" width="100%" height="700" preserveAspectRatio="xMidYMid meet" style="display:block;background:#f8fafc">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="#94a3b8"></path>
        </marker>
      </defs>
      ${edgeLines}
      ${nodeEls}
    </svg>`;
}

function bindNeo4jGraphInteractions(root, onSelect, onExpand) {
  root?.querySelectorAll('.neo4j-node').forEach((node) => {
    node.addEventListener('mouseenter', () => {
      node.querySelector('circle')?.setAttribute('stroke-width', '3');
    });
    node.addEventListener('mouseleave', () => {
      const selected = node.classList.contains('selected');
      node.querySelector('circle')?.setAttribute('stroke-width', selected ? '3' : '1.6');
    });
    node.addEventListener('click', () => {
      const id = node.dataset.nodeId;
      const label = node.dataset.nodeLabel || id;
      if (!id) return;
      onSelect?.(id, label);
    });
    node.addEventListener('dblclick', () => {
      const id = node.dataset.nodeId;
      const label = node.dataset.nodeLabel || id;
      if (id) onExpand?.(id, label);
    });
  });
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
      const metaLine = [s.subtitle, s.source_label, s.locator].filter(Boolean).join(' · ');
      html = `
        <div class="ref-head"><span class="k">Reference</span><button type="button" class="see" data-see-all>See All (${seeCount})</button></div>
        <div class="ref-title">${escapeHtml(s.display_title || s.printed_page_code || s.source_id || 'Source')}</div>
        <div class="ref-meta"><span>${escapeHtml(metaLine || 'NCCN B-Cell Lymphomas')}</span><span class="badge">${escapeHtml(s.badge || (s.page_type === 'clinical_guideline' ? '指南' : (s.page_type || 'Guideline')))}</span></div>
        <div class="muted small" style="margin-top:8px">${escapeHtml((s.text || s.section || '').slice(0, 180))}</div>`;
    } else if (type === 'G') {
      const g = (payload.graph_triples || [])[Number(btn.dataset.index)] || {};
      html = `
        <div class="ref-head"><span class="k">Graph</span><button type="button" class="see" data-see-all>See All</button></div>
        <div class="ref-title">${escapeHtml(g.subject_name || '')} → ${escapeHtml(g.relation || '')} → ${escapeHtml(g.object_name || '')}</div>
        <div class="ref-meta"><span>confidence ${Number(g.confidence || 0).toFixed(2)}</span><span class="badge">${escapeHtml(g.validation_status || 'graph')}</span></div>
        <div class="muted small" style="margin-top:8px;max-width:320px;white-space:pre-wrap">${escapeHtml((g.evidence_text || '').slice(0, 220))}</div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn primary" data-open-neo4j>查看图谱</button>
        </div>`;
    } else {
      const r = (payload.attached_references || []).find((x) => String(x.ref_number) === String(btn.dataset.ref)) || {};
      const metaLine = r.source_label || [r.journal, r.year, r.authors].filter(Boolean).join('. ') || (r.pmid ? `PMID ${r.pmid}` : 'Literature');
      html = `
        <div class="ref-head"><span class="k">Reference</span><button type="button" class="see" data-see-all>See All (${seeCount})</button></div>
        <div class="ref-title">${escapeHtml(r.display_title || (r.text || '').slice(0, 160))}</div>
        <div class="ref-meta"><span>${escapeHtml(metaLine)}</span><span class="badge">${escapeHtml(r.badge || '文献')}</span></div>`;
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
    pop.querySelector('[data-open-neo4j]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const g = (payload.graph_triples || [])[Number(btn.dataset.index)] || {};
      const seed = g.subject_name || g.object_name || payload.standalone_question || payload.question || '';
      openToolsDrawer('neo4j', seed);
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
  els.chatLog.querySelectorAll('.msg-row').forEach((node) => {
    const idx = Number(node.dataset.msgIdx);
    const msg = state.messages[idx] || getNode(node.dataset.nodeId);
    if (!msg) return;

    node.querySelectorAll('[data-act]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const act = btn.dataset.act;

        if (act === 'prev-branch' || act === 'next-branch') {
          await switchBranch(msg, act === 'prev-branch' ? -1 : 1);
          return;
        }
        if (act === 'del-branch') {
          if (state.isSubmitting) return;
          const multi = siblingsOf(msg).length > 1;
          const tip = multi
            ? '删除此分支及其后续对话？其他版本会保留。'
            : (msg.role === 'user'
              ? '删除此问题及其后续对话？'
              : '删除此回答及其后续对话？');
          if (!confirm(tip)) return;
          await deleteBranch(msg);
          return;
        }

        if (msg.role === 'user') {
          if (act === 'copy-user') {
            try {
              await copyTextToClipboard(msg.content || '');
              flashActionIcon(btn, 'check', '已复制', ICON.copy, '复制', 1000);
            } catch {
              alert('复制失败，请手动选择文本复制');
            }
            return;
          }
          if (act === 'edit') {
            if (state.isSubmitting) return;
            Object.values(state.tree.nodesById).forEach((m) => { if (m.role === 'user') m.editing = false; });
            msg.editing = true;
            renderChat();
            return;
          }
          if (act === 'edit-cancel') {
            msg.editing = false;
            renderChat();
            return;
          }
          if (act === 'edit-send') {
            const input = node.querySelector('.user-edit-input');
            const next = String(input?.value || '').trim();
            if (!next) return;
            if (next === String(msg.content || '').trim()) {
              msg.editing = false;
              renderChat();
              return;
            }
            askQuestion(next, { editFromNodeId: msg.id });
            return;
          }
          return;
        }

        // assistant
        if (act === 'copy') {
          const text = msg.payload?.answer_markdown || msg.content || '';
          try {
            await copyTextToClipboard(text);
            flashActionIcon(btn, 'check', '已复制', ICON.copy, '复制', 1000);
          } catch {
            alert('复制失败，请手动选择文本复制');
          }
        } else if (act === 'regen') {
          if (state.isSubmitting) return;
          const userMsg = getNode(msg.parentId);
          if (userMsg?.role === 'user') {
            askQuestion(userMsg.content, { regenerate: true, userNodeId: userMsg.id });
          }
        } else if (act === 'up' || act === 'down') {
          const value = msg.feedback === act ? null : act;
          const serverId = msg.serverId || null;
          if (state.user && serverId) {
            const resp = await api(`/api/messages/${serverId}/feedback`, {
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
          const url = await createShareLink({ messageId: msg.serverId || null });
          if (!url) return;
          await copyShareLink(url, btn, ICON.share, '分享此回答');
        }
      });
    });
  });
}

function setAskBtnMode(mode) {
  if (!els.askBtn) return;
  if (mode === 'stop') {
    els.askBtn.classList.add('is-stopping');
    els.askBtn.textContent = '■';
    els.askBtn.setAttribute('aria-label', '停止生成');
    els.askBtn.disabled = false;
  } else {
    els.askBtn.classList.remove('is-stopping');
    els.askBtn.textContent = '➤';
    els.askBtn.setAttribute('aria-label', '发送');
    els.askBtn.disabled = false;
  }
}

function stopGeneration() {
  if (state.abortController) state.abortController.abort();
}

function emptyAnswerPayload(text) {
  return {
    answer_markdown: text,
    answer_paragraphs: [text],
    sources: [],
    figures: [],
    attached_references: [],
    reference_links: {},
    graph_triples: [],
  };
}

function finalizeStoppedAssistant(assistant) {
  // newChat() may have cleared tree after aborting; ignore stale assistants.
  if (!assistant || !getNode(assistant.id)) return;
  const partial = String(assistant.content || '').trim();
  if (assistant.pending || !partial) {
    assistant.pending = false;
    assistant.content = '已停止生成';
    assistant.payload = emptyAnswerPayload(assistant.content);
  } else {
    assistant.pending = false;
    if (!assistant.payload) {
      assistant.payload = emptyAnswerPayload(assistant.content);
    }
  }
  state.lastPayload = assistant.payload;
  rebuildActivePath();
  renderChat();
}

async function askQuestion(question, meta = {}) {
  const q = String(question || '').trim();
  if (!q || state.isSubmitting) return;
  state.isSubmitting = true;
  setAskBtnMode('stop');
  if (els.followUpInput) els.followUpInput.value = '';
  setComposerExpanded(false);

  let assistant = null;
  let userNode = null;
  let parentMessageId = null; // server id for API
  let regenerate = false;

  if (meta.editFromNodeId) {
    const oldUser = getNode(meta.editFromNodeId);
    if (!oldUser || oldUser.role !== 'user') {
      state.isSubmitting = false;
      setAskBtnMode('send');
      return;
    }
    oldUser.editing = false;
    const parent = getNode(oldUser.parentId);
    parentMessageId = parent?.serverId || null;
    userNode = createNode({
      role: 'user',
      content: q,
      parentId: oldUser.parentId,
    });
    assistant = createNode({
      role: 'assistant',
      content: '',
      parentId: userNode.id,
      pending: true,
    });
  } else if (meta.regenerate) {
    const user = getNode(meta.userNodeId) || (() => {
      const last = state.messages.at(-1);
      return last?.role === 'assistant' ? getNode(last.parentId) : null;
    })();
    if (!user || user.role !== 'user') {
      state.isSubmitting = false;
      setAskBtnMode('send');
      return;
    }
    regenerate = true;
    parentMessageId = user.serverId || null;
    userNode = user;
    assistant = createNode({
      role: 'assistant',
      content: '',
      parentId: user.id,
      pending: true,
    });
  } else {
    const leaf = state.messages.length ? state.messages[state.messages.length - 1] : null;
    const parentId = leaf && !leaf.pending ? leaf.id : null;
    parentMessageId = leaf && !leaf.pending ? (leaf.serverId || null) : null;
    userNode = createNode({
      role: 'user',
      content: q,
      parentId,
    });
    assistant = createNode({
      role: 'assistant',
      content: '',
      parentId: userNode.id,
      pending: true,
    });
  }

  rebuildActivePath();
  renderChat();

  if (state.abortController) state.abortController.abort();
  state.abortController = new AbortController();

  try {
    // Active path without pending bubbles; drop current user turn (sent as `question`).
    const history = state.messages
      .filter((m) => !m.pending)
      .slice(0, -1)
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
        parent_message_id: parentMessageId,
        regenerate,
        data_source: state.dataSource || 'nccn',
      }),
      signal: state.abortController.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const ctype = resp.headers.get('content-type') || '';
    if (ctype.includes('text/event-stream') && resp.body) {
      await consumeSSE(resp, assistant, userNode);
    } else {
      const data = await resp.json();
      finalizeAssistant(assistant, data, userNode);
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      finalizeStoppedAssistant(assistant);
    } else {
      assistant.pending = false;
      assistant.content = '请求失败，请稍后重试。';
      assistant.payload = emptyAnswerPayload(assistant.content);
      state.lastPayload = assistant.payload;
      rebuildActivePath();
      renderChat();
    }
  } finally {
    state.isSubmitting = false;
    setAskBtnMode('send');
    persistChatState();
    renderChat();
    if (state.user) await loadConversations();
    else renderHistory();
  }
}

async function consumeSSE(resp, assistant, userNode = null) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let answer = '';
  const answerEl = () => els.chatLog.querySelector('.msg-row.assistant:last-of-type .answer');
  const msgEl = () => els.chatLog.querySelector('.msg-row.assistant:last-of-type');

  const paintStatus = () => {
    if (!assistant.pending) return;
    const el = msgEl();
    if (!el) return;
    // Re-render only this pending bubble for live status steps.
    const idx = Number(el.dataset.msgIdx);
    if (Number.isFinite(idx)) {
      el.outerHTML = renderMessage(assistant, idx);
      bindMessageActions();
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
      } else if (event.type === 'cite_context') {
        assistant.citePayload = {
          sources: event.sources || [],
          attached_references: event.attached_references || [],
        };
      } else if (event.type === 'token') {
        answer += event.text || '';
        assistant.content = answer;
        assistant.pending = false;
        const el = answerEl();
        const citeCtx = assistant.citePayload || state.lastPayload || {};
        if (el) el.innerHTML = decorateCitations(renderMarkdown(answer), citeCtx);
        else renderChat();
        els.chatLog.scrollTop = els.chatLog.scrollHeight;
      } else if (event.type === 'final') {
        finalizeAssistant(assistant, event.payload || {}, userNode);
        return;
      }
    }
  }
}

function finalizeAssistant(assistant, payload, userNode = null) {
  if (!assistant || !getNode(assistant.id)) return;
  assistant.pending = false;
  if (payload && !payload.data_source) {
    payload.data_source = state.dataSource || 'nccn';
  }
  assistant.payload = payload;
  assistant.dataSource = payload?.data_source || state.dataSource;
  assistant.content = payload.answer_markdown || assistant.content || '';
  if (payload.assistant_message_id) {
    assistant.serverId = payload.assistant_message_id;
  }
  const user = userNode || getNode(assistant.parentId);
  if (user && payload.user_message_id) {
    user.serverId = payload.user_message_id;
  }
  if (payload.conversation_id) {
    if (state.user) {
      state.activeConversationId = payload.conversation_id;
    } else if (!isLocalConversationId(state.activeConversationId)) {
      // Guests keep local-* ids; ignore server ids if any.
      state.activeConversationId = state.activeConversationId || newLocalConversationId();
    }
  }
  state.lastPayload = payload;
  rebuildActivePath();
  persistChatState();
  renderChat();
}

function openToolsDrawer(kind, seedOverride = '') {
  const payload = state.lastPayload;
  if (!payload) { alert('请先完成一次问答'); return; }
  const overlay = document.createElement('div');
  overlay.className = 'drawer-overlay';
  let body = '';
  if (kind === 'trace') {
    body = `<pre style="white-space:pre-wrap;font-size:12px">${escapeHtml(JSON.stringify(payload.trace || {}, null, 2))}</pre>`;
  } else if (kind === 'sources') {
    body = (payload.sources || []).map((s, i) => `
      <div class="evidence-card"><strong>${escapeHtml(s.citation_label || s.printed_page_code || s.source_id || `Source ${i + 1}`)}</strong>
      <div class="muted small">${escapeHtml(s.source_label || s.page_type || '')}${s.locator ? ` · ${escapeHtml(s.locator)}` : ''}</div>
      ${s.subtitle ? `<div class="muted small" style="margin-top:4px">${escapeHtml(s.subtitle)}</div>` : ''}
      <div style="margin-top:8px">${escapeHtml((s.text || '').slice(0, 400))}</div></div>`).join('') || '<div class="muted">无证据</div>';
  } else if (kind === 'graph') {
    body = (payload.graph_triples || []).map((g, i) => `
      <div class="evidence-card">
        <div><button class="cite" data-cite="G" data-index="${i}">G${i + 1}</button> <strong>${escapeHtml(g.subject_name)}</strong> → ${escapeHtml(g.relation)} → <strong>${escapeHtml(g.object_name)}</strong></div>
        <div class="muted small">confidence ${Number(g.confidence || 0).toFixed(2)} · ${escapeHtml(g.evidence_kind || 'graph')}</div>
      </div>`).join('') || '<div class="muted">无图谱</div>';
  } else if (kind === 'neo4j') {
    const seeds = Array.isArray(payload.graph_seed_candidates) ? payload.graph_seed_candidates : [];
    const initialSeed = (seedOverride || seeds[0] || '').trim();
    body = `
      <div class="evidence-card">
        <div class="muted small">推荐 seed</div>
        <div id="neo4jSeedList" class="template-row" style="justify-content:flex-start; margin-top:10px;">
          ${seeds.map((s) => `<button class="template-pill" data-seed="${escapeHtml(String(s))}">${escapeHtml(String(s))}</button>`).join('') || '<span class="muted">暂无推荐 seed</span>'}
        </div>
        <div style="display:flex; gap:10px; margin-top:12px; align-items:center; flex-wrap:wrap;">
          <input id="neo4jSeedInput" value="${escapeHtml(initialSeed)}" placeholder="输入实体名 / 页面码" style="flex:1; min-width:220px; padding:10px 12px; border-radius:12px; border:1px solid rgba(0,0,0,.1); font:inherit;" />
          <button class="btn primary" id="loadNeo4jGraphBtn">加载图谱</button>
          <button class="btn" id="neo4jResetBtn">重置</button>
          <button class="btn" id="neo4jCenterBtn">居中</button>
          <button class="btn" id="neo4jZoomInBtn">放大</button>
          <button class="btn" id="neo4jZoomOutBtn">缩小</button>
        </div>
      </div>
      <div class="neo4j-shell" style="display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:12px;align-items:start;">
        <div id="neo4jGraphCanvas" class="evidence-card" style="min-height:640px; overflow:auto;">${escapeHtml('正在加载...')}</div>
        <aside id="neo4jSidePanel" class="evidence-card" style="position:sticky;top:12px;min-height:640px;max-height:640px;overflow:auto;padding:14px;">
          <div class="ref-title" style="margin-bottom:10px">图谱概览</div>
          <div style="display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
            <button class="btn" id="neo4jPathBtn">路径模式</button>
            <button class="btn" id="neo4jOverviewBtn">概览模式</button>
          </div>
          <div id="neo4jStats" class="muted small">加载后显示统计信息</div>
          <div id="neo4jNodeDetail" style="margin-top:14px"></div>
        </aside>
      </div>`;
  } else {
    body = (payload.figures || []).map((f, i) => renderFigureCard(f, `tool-${i}`)).join('') || '<div class="muted">无流程图</div>';
  }
  const drawerWide = kind === 'neo4j' ? ' drawer-panel-wide' : '';
  overlay.innerHTML = `
    <div class="drawer-panel${drawerWide}">
      <div class="drawer-header">
        <div style="display:flex;align-items:center;gap:8px;">
          ${kind === 'neo4j' ? '<button class="btn" id="neo4jBackTopBtn" title="返回" aria-label="返回" style="padding:8px 10px; min-width:40px; line-height:1; font-size:16px">←</button>' : ''}
          <strong>${escapeHtml(kind)}</strong>
        </div>
        <button class="btn" id="closeToolsDrawer">关闭</button>
      </div>
      <div class="drawer-content">${body}</div>
    </div>`;
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
  document.getElementById('closeToolsDrawer')?.addEventListener('click', () => overlay.remove());
  overlay.querySelectorAll('[data-fig-open]').forEach((el) => {
    el.addEventListener('click', () => openLightbox(el.getAttribute('data-fig-open'), ''));
  });
  if (kind === 'neo4j') {
    const seedInput = overlay.querySelector('#neo4jSeedInput');
    const canvas = overlay.querySelector('#neo4jGraphCanvas');
    const loadBtn = overlay.querySelector('#loadNeo4jGraphBtn');
    const resetBtn = overlay.querySelector('#neo4jResetBtn');
    const centerBtn = overlay.querySelector('#neo4jCenterBtn');
    const zoomInBtn = overlay.querySelector('#neo4jZoomInBtn');
    const zoomOutBtn = overlay.querySelector('#neo4jZoomOutBtn');
    const backBtn = overlay.querySelector('#neo4jBackBtn');
    const backTopBtn = overlay.querySelector('#neo4jBackTopBtn');
    const homeBtn = overlay.querySelector('#neo4jHomeBtn');
    const pathBtn = overlay.querySelector('#neo4jPathBtn');
    const overviewBtn = overlay.querySelector('#neo4jOverviewBtn');
    const seedPills = overlay.querySelectorAll('[data-seed]');
    const statsEl = overlay.querySelector('#neo4jStats');
    const detailEl = overlay.querySelector('#neo4jNodeDetail');
    let currentSeed = '';
    let currentData = null;
    let currentScale = 1;
    let selectedNodeId = '';
    const historyStack = [];
    let mode = 'path';
    const renderStats = (data) => {
      if (!statsEl || !data) return;
      const projected = projectClinicalGraph(data || {});
      const pNodes = projected.nodes || [];
      const pEdges = projected.edges || [];
      const typeCounts = pNodes.reduce((acc, n) => {
        const k = String(n.type || 'Concept');
        acc[k] = (acc[k] || 0) + 1;
        return acc;
      }, {});
      const relCounts = pEdges.reduce((acc, e) => {
        const k = String(e.label || e.type || 'EDGE');
        acc[k] = (acc[k] || 0) + 1;
        return acc;
      }, {});
      const centerLabel = pNodes.find((n) => String(n.id) === String(projected.center))?.displayLabel
        || projected.center
        || currentSeed
        || '';
      const pathCount = Array.isArray(window.__GF_GRAPH_FOCUS__) ? window.__GF_GRAPH_FOCUS__.length : 0;
      statsEl.innerHTML = `
        <div><strong>模式</strong> ${mode === 'path' ? '路径模式' : '概览模式'}</div>
        <div><strong>中心节点</strong> ${escapeHtml(String(centerLabel))}</div>
        <div><strong>概念节点</strong> ${pNodes.length} · <strong>临床关系</strong> ${pEdges.length}</div>
        <div><strong>高亮路径</strong> ${pathCount}</div>
        <div class="muted small" style="margin-top:6px">单击查看详情 · 双击展开邻域 · 点“返回”回退</div>
        <div style="margin-top:10px"><strong>节点类型</strong><br>${Object.entries(typeCounts).slice(0, 6).map(([k, v]) => `<span class="badge" style="margin-right:6px;margin-top:6px;display:inline-block">${escapeHtml(k)} ${v}</span>`).join('') || '<span class="muted">无</span>'}</div>
        <div style="margin-top:10px"><strong>关系类型</strong><br>${Object.entries(relCounts).slice(0, 8).map(([k, v]) => `<span class="badge" style="margin-right:6px;margin-top:6px;display:inline-block">${escapeHtml(k)} ${v}</span>`).join('') || '<span class="muted">无</span>'}</div>`;
    };
    const renderDetail = (node) => {
      if (!detailEl) return;
      if (!node) {
        detailEl.innerHTML = '<div class="muted">点击一个节点查看详情</div>';
        return;
      }
      const props = node.properties && typeof node.properties === 'object' ? node.properties : {};
      const preferKeys = ['name', 'title', 'relation', 'subject_name', 'object_name', 'evidence_text', 'text', 'ref_number', 'article_id', 'page_code', 'printed_page_code'];
      const entries = [];
      for (const k of preferKeys) {
        if (props[k] != null && String(props[k]).trim()) entries.push([k, props[k]]);
      }
      for (const [k, v] of Object.entries(props)) {
        if (preferKeys.includes(k) || k === 'original_ids') continue;
        if (entries.length >= 8) break;
        entries.push([k, v]);
      }
      const items = entries.map(([k, v]) => `<div><strong>${escapeHtml(k)}</strong>: ${escapeHtml(String(v).slice(0, 180))}</div>`).join('');
      detailEl.innerHTML = `
        <div class="ref-title">${escapeHtml(String(node.displayLabel || node.label || node.id || 'Node'))}</div>
        <div class="muted small">类型：${escapeHtml(String(node.type || ''))}</div>
        <div class="muted small">节点键：${escapeHtml(String(node.id || ''))}</div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn primary" id="neo4jExpandNodeBtn">展开此节点</button>
        </div>
        <div style="margin-top:10px">${items || '<div class="muted">无属性</div>'}</div>`;
      detailEl.querySelector('#neo4jExpandNodeBtn')?.addEventListener('click', () => {
        navigateTo(node.displayLabel || node.id, 1, true);
      });
    };
    const paintCanvas = () => {
      if (!canvas || !currentData) return;
      const projected = projectClinicalGraph(currentData, Array.isArray(window.__GF_GRAPH_FOCUS__) ? window.__GF_GRAPH_FOCUS__ : []);
      selectedNodeId = selectedNodeId || projected.center || '';
      canvas.innerHTML = renderNeo4jGraph(currentData, selectedNodeId);
      canvas.style.transform = `scale(${currentScale})`;
      canvas.style.transformOrigin = 'top center';
      bindNeo4jGraphInteractions(
        canvas,
        (nodeId) => {
          selectedNodeId = nodeId;
          const p = projectClinicalGraph(currentData);
          const selected = (p.nodes || []).find((n) => String(n.id) === String(nodeId));
          paintCanvas();
          renderDetail(selected || null);
          renderStats(currentData);
        },
        (_nodeId, label) => {
          navigateTo(label || _nodeId, 1, true);
        },
      );
      const p = projectClinicalGraph(currentData);
      const selected = (p.nodes || []).find((n) => String(n.id) === String(selectedNodeId));
      renderDetail(selected || null);
      renderStats(currentData);
      if (backBtn) backBtn.disabled = historyStack.length === 0;
    };
    const navigateTo = async (seed, depth = 1, pushHistory = false) => {
      if (!seedInput || !canvas) return;
      const next = String(seed || '').trim();
      if (!next) {
        canvas.innerHTML = '<div class="muted" style="padding:16px">请输入一个实体名（如 DLBCL、TP53、R-CHOP），不要用纯数字 ID。</div>';
        return;
      }
      if (pushHistory && currentSeed) historyStack.push({ seed: currentSeed, scale: currentScale, selectedNodeId });
      canvas.innerHTML = '<div class="muted" style="padding:16px">加载中...</div>';
      currentSeed = next;
      if (seedInput) seedInput.value = next;
      try {
        const depthOverride = mode === 'overview' ? Math.max(depth, 2) : depth;
        const limit = mode === 'overview' ? 120 : 60;
        const resp = await api(`/api/graph/neighborhood?seed=${encodeURIComponent(next)}&limit=${limit}&depth=${depthOverride}`, { method: 'GET' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(formatApiDetail(data));
        currentData = data;
        selectedNodeId = '';
        if (mode === 'path') {
          const first = (projectClinicalGraph(data).nodes || [])[0];
          if (first) selectedNodeId = first.id;
        }
        paintCanvas();
      } catch (err) {
        canvas.innerHTML = `<div class="muted" style="padding:16px">加载失败：${escapeHtml(err?.message || 'unknown error')}<br><span class="small">提示：请用临床实体名作 seed（DLBCL / Biopsy / TP53），不要点纯数字文献编号。</span></div>`;
      }
    };
    const goBack = () => {
      const prev = historyStack.pop();
      if (!prev) return;
      currentScale = prev.scale || 1;
      selectedNodeId = prev.selectedNodeId || '';
      void navigateTo(prev.seed, 1, false);
    };
    loadBtn?.addEventListener('click', () => navigateTo(seedInput?.value || '', 1, true));
    resetBtn?.addEventListener('click', () => { currentScale = 1; selectedNodeId = ''; historyStack.length = 0; navigateTo(currentSeed || (seedInput?.value || ''), 1, false); });
    centerBtn?.addEventListener('click', () => paintCanvas());
    homeBtn?.addEventListener('click', () => paintCanvas());
    backBtn?.addEventListener('click', goBack);
    backTopBtn?.addEventListener('click', goBack);
    pathBtn?.addEventListener('click', () => { mode = 'path'; navigateTo(currentSeed || seedInput?.value || '', 1, false); });
    overviewBtn?.addEventListener('click', () => { mode = 'overview'; navigateTo(currentSeed || seedInput?.value || '', 2, false); });
    zoomInBtn?.addEventListener('click', () => { currentScale = Math.min(1.8, currentScale + 0.1); if (canvas) canvas.style.transform = `scale(${currentScale})`; });
    zoomOutBtn?.addEventListener('click', () => { currentScale = Math.max(0.6, currentScale - 0.1); if (canvas) canvas.style.transform = `scale(${currentScale})`; });
    seedPills.forEach((pill) => pill.addEventListener('click', () => navigateTo(pill.dataset.seed || '', 1, true)));
    const payloadSeeds = Array.isArray(payload.graph_seed_candidates) ? payload.graph_seed_candidates.filter(Boolean) : [];
    if (payloadSeeds.length) {
      const seedList = overlay.querySelector('#neo4jSeedList');
      if (seedList) {
        seedList.innerHTML = payloadSeeds.map((s) => `<button class="template-pill" data-seed="${escapeHtml(String(s))}">${escapeHtml(String(s))}</button>`).join('');
        seedList.querySelectorAll('[data-seed]').forEach((pill) => pill.addEventListener('click', () => navigateTo(pill.dataset.seed || '', 1, true)));
      }
      if (seedInput && !seedInput.value.trim()) seedInput.value = payloadSeeds[0];
      void navigateTo(payloadSeeds[0], 1, false);
    } else {
      void navigateTo(seedInput?.value || '', 1, false);
    }
  }
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

els.askBtn?.addEventListener('click', () => {
  if (state.isSubmitting) {
    stopGeneration();
    return;
  }
  askQuestion(els.followUpInput.value);
});
if (els.dataSourceSelect) {
  els.dataSourceSelect.value = state.dataSource;
  els.dataSourceSelect.addEventListener('change', () => {
    state.dataSource = saveDataSource(els.dataSourceSelect.value);
  });
}
els.followUpInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (state.isSubmitting) return;
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
