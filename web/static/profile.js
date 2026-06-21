/* Ronny — Profile page */

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

function renderCallLogs(calls) {
  if (!calls || calls.length === 0) {
    callLogList.innerHTML = '<p class="contact-empty">No calls placed yet.</p>';
    return;
  }
  callLogList.innerHTML = '';
  for (const call of calls) {
    const item = document.createElement('div');
    item.className = 'call-log-item';

    const ts = call.ts ? call.ts.replace('T', ' ').slice(0, 16) : '';
    const contact = call.contact || call.phone || 'Unknown';
    const status = call.status || 'unknown';
    const turns = Array.isArray(call.transcript) ? call.transcript : [];
    const contactInitial = contact[0].toUpperCase();

    // Header (always visible, click to expand)
    const header = document.createElement('div');
    header.className = 'call-log-header';
    header.innerHTML = `
      <span class="call-log-contact">${esc(contact)}</span>
      <span class="call-log-meta">
        <span class="call-log-pill ${esc(status)}">${esc(status)}</span>
        <span class="call-log-ts">${esc(ts)}</span>
      </span>
      <svg class="call-log-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="9 18 15 12 9 6"/>
      </svg>`;

    // Body (transcript, hidden by default)
    const body = document.createElement('div');
    body.className = 'call-log-body';

    if (call.mission) {
      const m = document.createElement('p');
      m.className = 'call-log-mission';
      m.textContent = call.mission;
      body.appendChild(m);
    }

    if (turns.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'call-no-transcript';
      empty.textContent = 'No transcript captured for this call.';
      body.appendChild(empty);
    } else {
      for (const turn of turns) {
        const div = document.createElement('div');
        div.className = `call-turn ${esc(turn.role)}`;
        div.innerHTML = `
          <div class="call-turn-avatar">${turn.role === 'assistant' ? 'AI' : esc(contactInitial)}</div>
          <div class="call-turn-bubble">${esc(turn.text)}</div>`;
        body.appendChild(div);
      }
    }

    header.addEventListener('click', () => {
      item.classList.toggle('open');
    });

    item.appendChild(header);
    item.appendChild(body);
    callLogList.appendChild(item);
  }
}

// ============================================================
// Init
// ============================================================
loadProfile();
loadContacts();
loadCallLogs();
