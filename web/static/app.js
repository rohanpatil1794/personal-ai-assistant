/* Ronny — Voice-first minimalist UI */

const sphere         = document.getElementById('sphere');
const statusDot      = document.getElementById('status-dot');
const statusLabel    = document.getElementById('status-label');
const waveform       = document.getElementById('waveform');
const pttBtn         = document.getElementById('ptt-btn');
const pttLabel       = document.getElementById('ptt-label');
const textInput      = document.getElementById('text-input');
const sendBtn        = document.getElementById('send-btn');
const emptyState     = document.getElementById('empty-state');
const captionEl      = document.getElementById('caption');
const capUser        = document.getElementById('caption-user');
const capAssistant   = document.getElementById('caption-assistant');
const orderBar       = document.getElementById('order-bar');
const orderBarText   = document.getElementById('order-bar-text');
const orderBarTimer  = document.getElementById('order-bar-timer');
const orderConfirmBtn= document.getElementById('order-confirm-btn');
const orderCancelBtn = document.getElementById('order-cancel-btn');

let state = 'idle';
let mediaRecorder = null;
let audioChunks = [];
let audioCtx = null;
let busy = false;
let captionTimer = null;
let orderDismissTimer = null;

// ============================================================
// State machine
// ============================================================

const LABELS = {
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
  statusLabel.textContent = customLabel ?? LABELS[s] ?? s;
  waveform.classList.toggle('active', s === 'listening');

  if (s === 'listening') {
    pttBtn.classList.add('listening');
    pttLabel.textContent = 'Release to send';
  } else {
    pttBtn.classList.remove('listening');
    pttLabel.textContent = 'Hold to talk';
  }

  const locked = s === 'thinking' || s === 'speaking';
  textInput.disabled = locked;
  sendBtn.disabled   = locked;
}

// ============================================================
// Caption system — shows text then fades after delay
// ============================================================

function showCaption(userText, assistantText) {
  // Clear any existing fade timer
  if (captionTimer) clearTimeout(captionTimer);

  // Hide empty state
  emptyState.style.opacity = '0';
  emptyState.style.pointerEvents = 'none';

  // Set user text (if any)
  if (userText) {
    capUser.textContent = userText;
    capUser.classList.add('visible');
  } else {
    capUser.classList.remove('visible');
    capUser.textContent = '';
  }

  // Set assistant text
  capAssistant.textContent = assistantText;
  capAssistant.classList.add('visible');

  // Auto-fade after 5s
  captionTimer = setTimeout(clearCaption, 5000);
}

function clearCaption() {
  capUser.classList.remove('visible');
  capAssistant.classList.remove('visible');
  captionTimer = setTimeout(() => {
    capUser.textContent = '';
    capAssistant.textContent = '';
    emptyState.style.opacity = '';
    emptyState.style.pointerEvents = '';
  }, 400);
}

// ============================================================
// Order confirmation bar — slides up, auto-dismisses in 15s
// ============================================================

const ORDER_TIMEOUT = 15000;

function showOrderBar(orderSummary) {
  // Build a compact summary string
  let summary = 'Order ready · COD';
  try {
    const items = orderSummary.items || orderSummary.cart?.items || [];
    if (items.length) {
      const names = items.slice(0, 2).map(i => i.name || i.itemName || 'Item').join(', ');
      const total = orderSummary.total || orderSummary.bill?.total || orderSummary.cart?.total;
      summary = names + (total ? ` · ₹${total}` : '') + ' · COD';
    }
  } catch { /* use default */ }

  orderBarText.textContent = summary;
  orderBar.classList.add('visible');
  orderBar.setAttribute('aria-hidden', 'false');
  orderConfirmBtn.focus();

  // Animate timer bar shrinking over ORDER_TIMEOUT ms
  orderBarTimer.style.transition = 'none';
  orderBarTimer.style.transform = 'scaleX(1)';
  // Force reflow then start shrink
  orderBarTimer.getBoundingClientRect();
  orderBarTimer.style.transition = `transform ${ORDER_TIMEOUT}ms linear`;
  orderBarTimer.style.transform = 'scaleX(0)';

  orderDismissTimer = setTimeout(() => {
    hideOrderBar();
    sendText('cancel the order');
  }, ORDER_TIMEOUT);
}

function hideOrderBar() {
  clearTimeout(orderDismissTimer);
  orderBar.classList.remove('visible');
  orderBar.setAttribute('aria-hidden', 'true');
  orderBarTimer.style.transition = 'none';
  orderBarTimer.style.transform = 'scaleX(0)';
}

orderConfirmBtn.addEventListener('click', () => {
  hideOrderBar();
  sendText('__confirm_order__');
});

orderCancelBtn.addEventListener('click', () => {
  hideOrderBar();
  sendText('cancel the order');
});

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

async function handleResponse(data, userText) {
  // Show caption (user text + assistant reply)
  showCaption(userText || data.transcript || null, data.reply);

  // Order confirmation bar instead of modal
  if (data.confirmation_required && data.order_summary) {
    showOrderBar(data.order_summary);
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
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    await handleResponse(data, data.transcript);
  } catch (e) {
    console.error(e);
    setState('error', e.message);
    setTimeout(() => setState('idle'), 3000);
  } finally {
    busy = false;
  }
}

async function sendText(text) {
  if (!text.trim() || busy) return;
  busy = true;

  const isSentinel = text === '__confirm_order__' || text === 'cancel the order';
  const displayText = isSentinel ? null : text;

  setState('thinking');
  try {
    const res = await fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    await handleResponse(data, displayText);
  } catch (e) {
    console.error(e);
    setState('error', e.message);
    setTimeout(() => setState('idle'), 3000);
  } finally {
    busy = false;
  }
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
    setState('error', 'Mic access denied');
    setTimeout(() => setState('idle'), 3000);
    return;
  }
  audioChunks = [];
  const mime = ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','']
    .find(m => !m || MediaRecorder.isTypeSupported(m));
  mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
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
// Event listeners
// ============================================================

// PTT
pttBtn.addEventListener('mousedown',  e => { e.preventDefault(); startRecording(); });
pttBtn.addEventListener('mouseup',    () => stopRecording());
pttBtn.addEventListener('mouseleave', () => stopRecording());
pttBtn.addEventListener('touchstart', e => { e.preventDefault(); startRecording(); }, { passive: false });
pttBtn.addEventListener('touchend',   e => { e.preventDefault(); stopRecording(); },  { passive: false });

// Spacebar
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && document.activeElement === document.body && !e.repeat) {
    e.preventDefault(); startRecording();
  }
});
document.addEventListener('keyup', e => { if (e.code === 'Space') stopRecording(); });

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
