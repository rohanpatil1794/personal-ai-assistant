/* Ronny — Settings page */

// ============================================================
// Tab switching
// ============================================================

const configTabs  = [...document.querySelectorAll('.config-tab')];
const configPanes = [...document.querySelectorAll('.config-pane')];

function switchTab(name) {
  configTabs.forEach(t => {
    const on = t.dataset.tab === name;
    t.classList.toggle('active', on);
    t.setAttribute('aria-selected', String(on));
  });
  configPanes.forEach(p => p.classList.toggle('active', p.id === `pane-${name}`));
  history.replaceState(null, '', '#' + name);
}

configTabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));

// Init from URL hash
const _initTab = location.hash.slice(1);
if (['profile', 'documents', 'calling'].includes(_initTab)) switchTab(_initTab);

// ============================================================

function apiHeaders(extra) {
  const token = window.RONNY_API_TOKEN;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

// ============================================================
// Personal Info
// ============================================================

const nameInput   = document.getElementById('profile-name');
const aboutInput  = document.getElementById('profile-about');
const saveBtn     = document.getElementById('profile-save-btn');

async function loadProfile() {
  try {
    const r = await fetch('/api/profile', { headers: apiHeaders() });
    if (!r.ok) return;
    const { name, about } = await r.json();
    nameInput.value  = name  || '';
    aboutInput.value = about || '';
  } catch {}
}

saveBtn.addEventListener('click', async () => {
  saveBtn.disabled = true;
  try {
    const r = await fetch('/api/profile', {
      method: 'POST',
      headers: apiHeaders(),
      body: JSON.stringify({ name: nameInput.value.trim(), about: aboutInput.value.trim() }),
    });
    if (r.ok) {
      saveBtn.textContent = 'Saved ✓';
      saveBtn.classList.add('saved');
      setTimeout(() => {
        saveBtn.textContent = 'Save';
        saveBtn.classList.remove('saved');
        saveBtn.disabled = false;
      }, 2000);
    } else {
      saveBtn.disabled = false;
    }
  } catch {
    saveBtn.disabled = false;
  }
});

// ============================================================
// Contacts
// ============================================================

const contactList     = document.getElementById('contact-list');
const contactNameIn   = document.getElementById('contact-name-input');
const contactPhoneIn  = document.getElementById('contact-phone-input');
const contactAddBtn   = document.getElementById('contact-add-btn');

async function loadContacts() {
  try {
    const r = await fetch('/api/contacts', { headers: apiHeaders() });
    if (!r.ok) return;
    const { contacts } = await r.json();
    renderContacts(contacts);
  } catch {}
}

function renderContacts(contacts) {
  contactList.innerHTML = '';
  const entries = Object.entries(contacts);
  if (entries.length === 0) {
    contactList.innerHTML = '<p class="contact-empty">No contacts yet. Add one below.</p>';
    return;
  }
  for (const [name, phone] of entries.sort((a, b) => a[0].localeCompare(b[0]))) {
    const row = document.createElement('div');
    row.className = 'contact-row';
    row.innerHTML = `
      <span class="contact-name">${esc(name)}</span>
      <span class="contact-phone">${esc(phone)}</span>
      <button class="contact-delete-btn" aria-label="Delete ${esc(name)}" data-name="${esc(name)}">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;
    row.querySelector('.contact-delete-btn').addEventListener('click', () => deleteContact(name));
    contactList.appendChild(row);
  }
}

async function deleteContact(name) {
  try {
    const r = await fetch(`/api/contacts/${encodeURIComponent(name)}`, {
      method: 'DELETE',
      headers: apiHeaders(),
    });
    if (r.ok) loadContacts();
  } catch {}
}

contactAddBtn.addEventListener('click', addContact);
contactPhoneIn.addEventListener('keydown', e => { if (e.key === 'Enter') addContact(); });
contactNameIn.addEventListener('keydown', e => { if (e.key === 'Enter') contactPhoneIn.focus(); });

async function addContact() {
  const name  = contactNameIn.value.trim();
  const phone = contactPhoneIn.value.trim();
  if (!name || !phone) return;

  contactAddBtn.disabled = true;
  try {
    const r = await fetch('/api/contacts', {
      method: 'POST',
      headers: apiHeaders(),
      body: JSON.stringify({ name, phone }),
    });
    if (r.ok) {
      contactNameIn.value  = '';
      contactPhoneIn.value = '';
      contactNameIn.focus();
      loadContacts();
    }
  } catch {}
  contactAddBtn.disabled = false;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ============================================================
// Call Logs
// ============================================================

const callLogList = document.getElementById('call-log-list');

async function loadCallLogs() {
  try {
    const r = await fetch('/api/call-logs', { headers: apiHeaders() });
    if (!r.ok) { callLogList.innerHTML = '<p class="contact-empty">Could not load call logs.</p>'; return; }
    const { calls } = await r.json();
    renderCallLogs(calls);
  } catch {
    callLogList.innerHTML = '<p class="contact-empty">Could not load call logs.</p>';
  }
}

function fmtTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const today = new Date();
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function fmtDuration(ts, completedAt) {
  if (!ts || !completedAt) return null;
  const secs = Math.round((new Date(completedAt) - new Date(ts)) / 1000);
  if (secs < 0) return null;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `0:${String(s).padStart(2, '0')}`;
}

function phoneIcon(status) {
  const color = (status === 'completed') ? 'var(--green)' : 'var(--red)';
  return `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="call-log-icon">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.63 3.36 2 2 0 0 1 3.6 1.18h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.77a16 16 0 0 0 6.29 6.29l.96-.96a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
  </svg>`;
}

function renderCallLogs(calls) {
  if (!calls || calls.length === 0) {
    callLogList.innerHTML = '<p class="contact-empty">No calls placed yet.</p>';
    return;
  }

  const list = document.createElement('div');
  list.className = 'call-log-list';

  for (const call of calls) {
    const contact = call.contact || call.phone || 'Unknown';
    const status = call.status || 'unknown';
    const initial = contact[0].toUpperCase();
    const duration = fmtDuration(call.ts, call.completed_at);
    const timeStr = fmtTime(call.ts);
    const dateStr = fmtDate(call.ts);
    const turns = Array.isArray(call.transcript) ? call.transcript : [];

    const subParts = [call.phone ? esc(call.phone) : null, dateStr, timeStr, duration].filter(Boolean);

    const item = document.createElement('div');
    item.className = `call-log-item status-${esc(status)}`;

    const header = document.createElement('div');
    header.className = 'call-log-header';
    header.innerHTML = `
      <div class="call-log-avatar">${esc(initial)}</div>
      <div class="call-log-info">
        <div class="call-log-name">${esc(contact)}</div>
        <div class="call-log-sub">${subParts.map((p, i) => i === 0 ? p : `<span class="call-log-sub-dot">·</span>${p}`).join('')}</div>
      </div>
      <div class="call-log-right">
        <span class="call-log-time">${esc(dateStr)}</span>
        ${phoneIcon(status)}
      </div>
      <svg class="call-log-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="9 18 15 12 9 6"/>
      </svg>`;

    const body = document.createElement('div');
    body.className = 'call-log-body';

    if (turns.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'call-no-transcript';
      empty.textContent = 'No transcript available for this call.';
      body.appendChild(empty);
    } else {
      for (const turn of turns) {
        const div = document.createElement('div');
        div.className = `call-turn ${esc(turn.role)}`;
        div.innerHTML = `<div class="call-turn-bubble">${esc(turn.text)}</div>`;
        body.appendChild(div);
      }
    }

    header.addEventListener('click', () => item.classList.toggle('open'));
    item.appendChild(header);
    item.appendChild(body);
    list.appendChild(item);
  }

  callLogList.innerHTML = '';
  callLogList.appendChild(list);
}

// ============================================================
// Init
// ============================================================
loadProfile();
loadContacts();
loadCallLogs();
