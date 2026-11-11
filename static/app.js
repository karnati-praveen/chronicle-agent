const sessionKey = 'chronicle.session.v1';
let sessionId = localStorage.getItem(sessionKey) || crypto.randomUUID().replaceAll('-', '');
localStorage.setItem(sessionKey, sessionId);
const chatEl = document.querySelector('#chat');
const welcomeEl = document.querySelector('#welcome');
const form = document.querySelector('#composer');
const input = document.querySelector('#message');
const send = document.querySelector('#send');
const historyEl = document.querySelector('#search-history');

function timeLabel(value) {
  try { return new Date(value).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}); }
  catch { return value || ''; }
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function safeTextWithLinks(text) {
  const escaped = escapeHtml(text);
  return escaped.replace(/(https?:\/\/[^\s<>]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
}
function hostnameOf(url) {
  try { return new URL(url).hostname; } catch { return ''; }
}
function safeHref(url) {
  const value = String(url || '');
  return /^https?:\/\//i.test(value) ? value : '';
}
function revealChat() { welcomeEl.classList.add('hidden'); chatEl.classList.remove('hidden'); }
function addMessage(role, content, createdAt, sources = []) {
  revealChat();
  const item = document.createElement('article');
  item.className = `message ${role}`;
  const who = role === 'user' ? 'You' : 'Chronicle';
  const avatar = role === 'user' ? 'Y' : '◷';
  let cards = '';
  const validSources = (sources || []).filter(s => safeHref(s.url));
  if (role === 'assistant' && validSources.length) {
    cards = `<div class="source-list">${validSources.map((s, i) => `<a class="source-card" href="${escapeHtml(safeHref(s.url))}" target="_blank" rel="noopener noreferrer"><strong>[${s.number || i+1}] ${escapeHtml(s.title || 'Source')}</strong><span>${escapeHtml(hostnameOf(s.url))}</span></a>`).join('')}</div>`;
  }
  item.innerHTML = `<div class="avatar">${avatar}</div><div class="message-body"><div class="message-head">${who}<time>${escapeHtml(timeLabel(createdAt))}</time></div><div class="message-content">${safeTextWithLinks(content)}</div>${cards}</div>`;
  chatEl.appendChild(item);
  chatEl.scrollTop = chatEl.scrollHeight;
}
function showTyping() {
  revealChat();
  const el = document.createElement('article');
  el.className = 'message'; el.id = 'typing';
  el.innerHTML = '<div class="avatar">◷</div><div class="message-body"><div class="message-head">Chronicle <time>working</time></div><div class="typing"><i></i><i></i><i></i></div></div>';
  chatEl.appendChild(el); chatEl.scrollTop = chatEl.scrollHeight;
}
function hideTyping() { document.querySelector('#typing')?.remove(); }
async function loadHistory() {
  try {
    const res = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.messages.length) {
      welcomeEl.classList.add('hidden'); chatEl.classList.remove('hidden');
      data.messages.forEach(m => addMessage(m.role, m.content, m.created_at, m.sources || []));
    }
    renderSearches(data.searches || []);
  } catch { /* Server may not be running yet. */ }
}
function renderSearches(searches) {
  if (!searches.length) return;
  historyEl.innerHTML = searches.map(s => `<div class="search-item">${escapeHtml(s.query)}<time>${escapeHtml(timeLabel(s.searched_at))} · ${s.result_count} results</time></div>`).join('');
}
async function submitMessage(text) {
  const message = (text || '').trim();
  if (!message || send.disabled) return;
  addMessage('user', message, new Date().toISOString());
  input.value = ''; input.style.height = 'auto';
  send.disabled = true; send.textContent = 'Thinking…'; showTyping();
  try {
    const res = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message, session_id: sessionId})
    });
    const data = await res.json();
    hideTyping();
    if (!res.ok) throw new Error(data.detail || 'The request failed.');
    sessionId = data.session_id; localStorage.setItem(sessionKey, sessionId);
    addMessage('assistant', data.answer, data.created_at, data.sources || []);
    const history = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`).then(r => r.json());
    renderSearches(history.searches || []);
  } catch (err) {
    hideTyping(); addMessage('assistant', `I couldn't complete that request: ${err.message}\n\nCheck your LLM and web-search keys in .env, then try again.`, new Date().toISOString());
  } finally { send.disabled = false; send.innerHTML = 'Send <span>↑</span>'; input.focus(); }
}
form.addEventListener('submit', e => { e.preventDefault(); submitMessage(input.value); });
input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 150)}px`; });
input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll('.suggestion').forEach(button => button.addEventListener('click', () => submitMessage(button.dataset.prompt)));
function resetConversation() {
  sessionId = crypto.randomUUID().replaceAll('-', ''); localStorage.setItem(sessionKey, sessionId);
  chatEl.innerHTML = ''; chatEl.classList.add('hidden'); welcomeEl.classList.remove('hidden');
  historyEl.innerHTML = '<p class="muted">Your searches will appear here.</p>';
}
document.querySelector('#new-chat').addEventListener('click', resetConversation);
document.querySelector('#export-chat').addEventListener('click', async () => {
  try {
    const res = await fetch(`/api/export?session_id=${encodeURIComponent(sessionId)}`);
    if (!res.ok) { alert('Nothing to export yet.'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `chronicle-export-${sessionId}.json`;
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  } catch { alert('Export failed. Is the server running?'); }
});
document.querySelector('#clear-chat').addEventListener('click', async () => {
  if (!confirm('Delete this conversation and all stored search records from the local database? This cannot be undone.')) return;
  try { await fetch(`/api/session?session_id=${encodeURIComponent(sessionId)}`, {method: 'DELETE'}); } catch { /* still reset locally */ }
  resetConversation();
});
loadHistory();
