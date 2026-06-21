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
// Init
// ============================================================
loadProfile();
loadContacts();
