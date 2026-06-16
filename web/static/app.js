/* Ronny web UI — state machine + MediaRecorder + AudioContext */

const sphere       = document.getElementById('sphere');
const statusDot    = document.getElementById('status-dot');
const statusLabel  = document.getElementById('status-label');
const waveform     = document.getElementById('waveform');
const messages     = document.getElementById('messages');
const chatPanel    = document.getElementById('chat-panel');
const pttBtn       = document.getElementById('ptt-btn');
const pttLabel     = document.getElementById('ptt-label');
const textInput    = document.getElementById('text-input');
const sendBtn      = document.getElementById('send-btn');
const confirmModal = document.getElementById('confirm-modal');
const confirmLines = document.getElementById('confirm-lines');
const confirmYes   = document.getElementById('confirm-yes');
const confirmNo    = document.getElementById('confirm-no');

// States: idle | listening | thinking | speaking | error
let state = 'idle';
let mediaRecorder = null;
let audioChunks = [];
let audioCtx = null;
let busy = false;

const STATE_LABELS = {
  idle:      'Hold Space or tap to speak',
  listening: 'Listening…',
  thinking:  'Thinking…',
  speaking:  'Speaking…',
  error:     'Something went wrong',
};

function setState(s, customLabel) {
  state = s;
  sphere.className = s;
  statusDot.className = `status-dot ${s}`;
  statusLabel.textContent = customLabel ?? STATE_LABELS[s] ?? s;

  // Waveform only during listening
  waveform.classList.toggle('active', s === 'listening');

  // PTT button appearance
  if (s === 'listening') {
    pttBtn.classList.add('listening');
    pttLabel.textContent = 'Release to Send';
  } else {
    pttBtn.classList.remove('listening');
    pttLabel.textContent = 'Hold to Talk';
  }

  // Disable controls while busy
  const isbusy = s === 'thinking' || s === 'speaking';
  textInput.disabled = isbusy;
  sendBtn.disabled = isbusy;
}

// ============================================================
// Chat messages
// ============================================================

const USER_ICON = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>`;
const BOT_ICON  = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>`;

function addMessage(role, text) {
  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.innerHTML = role === 'user' ? USER_ICON : BOT_ICON;
  avatar.setAttribute('aria-hidden', 'true');

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  messages.appendChild(wrap);
  chatPanel.scrollTop = chatPanel.scrollHeight;
}

// ============================================================
// Order confirmation modal
// ============================================================

function showConfirmModal(orderSummary) {
  let lines = '';
  try {
    const items = orderSummary.items || orderSummary.cart?.items || [];
    if (items.length) {
      lines = items.map(i => {
        const name  = i.name || i.itemName || i.productName || 'Item';
        const qty   = i.quantity ?? 1;
        const price = i.price != null ? `  ₹${i.price}` : '';
        return `${name} ×${qty}${price}`;
      }).join('\n');
    }
    const total = orderSummary.total || orderSummary.bill?.total || orderSummary.cart?.total;
    if (total != null) lines += `\n─────────────────\nTotal  ₹${total}`;
  } catch {
    lines = JSON.stringify(orderSummary, null, 2);
  }
  confirmLines.textContent = lines || 'See order details above.';
  confirmModal.classList.add('visible');
  confirmYes.focus();
}

function hideConfirmModal() {
  confirmModal.classList.remove('visible');
}

confirmYes.addEventListener('click', () => { hideConfirmModal(); sendText('__confirm_order__'); });
confirmNo.addEventListener('click',  () => { hideConfirmModal(); sendText('cancel the order'); });

// Close modal on backdrop click
confirmModal.addEventListener('click', e => { if (e.target === confirmModal) { hideConfirmModal(); sendText('cancel the order'); } });

// ============================================================
// Audio playback
// ============================================================

function getAudioCtx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return audioCtx;
}

async function playBase64Audio(b64) {
  const ctx = getAudioCtx();
  if (ctx.state === 'suspended') await ctx.resume();
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const buffer = await ctx.decodeAudioData(bytes.buffer);
  return new Promise(resolve => {
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.onended = resolve;
    src.start();
  });
}

// ============================================================
// Core pipeline
// ============================================================

async function handleResponse(data) {
  if (data.transcript) addMessage('user', data.transcript);
  addMessage('assistant', data.reply);

  if (data.confirmation_required && data.order_summary) {
    showConfirmModal(data.order_summary);
  }

  setState('speaking');
  await playBase64Audio(data.audio_b64);
  setState('idle');
}

async function sendVoiceBlob(blob) {
  busy = true;
  setState('thinking');
  try {
    const form = new FormData();
    form.append('file', blob, 'audio.webm');
    const res = await fetch('/api/voice', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    await handleResponse(await res.json());
  } catch (e) {
    console.error(e);
    setState('error', `Error: ${e.message}`);
    setTimeout(() => setState('idle'), 3000);
  } finally {
    busy = false;
  }
}

async function sendText(text) {
  if (!text.trim() || busy) return;
  busy = true;

  const isSentinel = text === '__confirm_order__' || text === 'cancel the order';
  if (!isSentinel) addMessage('user', text);

  setState('thinking');
  try {
    const res = await fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    addMessage('assistant', data.reply);
    if (data.confirmation_required && data.order_summary) {
      showConfirmModal(data.order_summary);
    }
    setState('speaking');
    await playBase64Audio(data.audio_b64);
  } catch (e) {
    console.error(e);
    setState('error', `Error: ${e.message}`);
    setTimeout(() => setState('idle'), 3000);
    return;
  } finally {
    busy = false;
  }
  setState('idle');
}

// ============================================================
// MediaRecorder
// ============================================================

async function startRecording() {
  if (busy || state === 'listening') return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    setState('error', 'Microphone access denied');
    setTimeout(() => setState('idle'), 3000);
    return;
  }
  audioChunks = [];
  const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', '']
    .find(m => !m || MediaRecorder.isTypeSupported(m));
  mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
  mediaRecorder.ondataavailable = e => { if (e.data.size) audioChunks.push(e.data); };
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach(t => t.stop());
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
    if (blob.size > 1000) sendVoiceBlob(blob);
    else setState('idle');
  };
  mediaRecorder.start();
  setState('listening');
}

function stopRecording() {
  if (state !== 'listening' || !mediaRecorder) return;
  mediaRecorder.stop();
}

// ============================================================
// Events
// ============================================================

// PTT
pttBtn.addEventListener('mousedown',  e => { e.preventDefault(); startRecording(); });
pttBtn.addEventListener('mouseup',    () => stopRecording());
pttBtn.addEventListener('mouseleave', () => stopRecording());
pttBtn.addEventListener('touchstart', e => { e.preventDefault(); startRecording(); }, { passive: false });
pttBtn.addEventListener('touchend',   e => { e.preventDefault(); stopRecording(); },  { passive: false });

// Spacebar PTT
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && e.target === document.body && !e.repeat) {
    e.preventDefault();
    startRecording();
  }
});
document.addEventListener('keyup', e => {
  if (e.code === 'Space') stopRecording();
});

// Text input
sendBtn.addEventListener('click', () => {
  const t = textInput.value.trim();
  if (!t) return;
  textInput.value = '';
  sendText(t);
});
textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    const t = textInput.value.trim();
    if (!t) return;
    textInput.value = '';
    sendText(t);
  }
});

// Resume AudioContext on first gesture
document.addEventListener('pointerdown', () => getAudioCtx().resume(), { once: true });
