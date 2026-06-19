/* Ronny — Voice-first minimalist UI */

function apiHeaders() {
  const token = window.RONNY_API_TOKEN;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const sphere          = document.getElementById('sphere');
const statusDot       = document.getElementById('status-dot');
const statusLabel     = document.getElementById('status-label');
const waveform        = document.getElementById('waveform');
const captionBox      = document.getElementById('caption-box');
const textInput       = document.getElementById('text-input');
const sendBtn         = document.getElementById('send-btn');
const orderBar        = document.getElementById('order-bar');
const orderBarText    = document.getElementById('order-bar-text');
const orderBarTimer   = document.getElementById('order-bar-timer');
const orderConfirmBtn = document.getElementById('order-confirm-btn');
const orderCancelBtn  = document.getElementById('order-cancel-btn');
const convBtn         = document.getElementById('conv-btn');
const convLabel       = document.getElementById('conv-label');

let state = 'idle';
let mediaRecorder = null;
let audioChunks = [];
let audioCtx = null;
let busy = false;
let orderDismissTimer = null;

// Caption state
let captionEl = null;
let captionFadeTimer = null;

// ============================================================
// VAD / Conversation mode
// ============================================================

const VAD_RMS_THRESHOLD     = 0.012;
const VAD_START_DEBOUNCE_MS = 200;
const VAD_STOP_DEBOUNCE_MS  = 1200;
const CONV_TIMEOUT_MS       = 120000;
const ARMED_PROMPT_MS       = 8000;
const ARMED_IDLE_MS         = 8000;

let convMode        = false;
let vadStream       = null;
let vadAnalyser     = null;
let vadRafId        = null;
let vadSpeaking     = false;
let vadSpeechStart  = 0;
let vadSilenceStart = 0;
let vadMediaRec     = null;
let vadChunks       = [];

let convTimeoutTimer  = null;
let armedPromptTimer  = null;
let armedIdleTimer    = null;

function computeRMS(analyser) {
  const buf = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

function resetArmedTimers() {
  clearTimeout(armedPromptTimer);
  clearTimeout(armedIdleTimer);
  armedPromptTimer = null;
  armedIdleTimer   = null;
}

function startArmedTimers() {
  resetArmedTimers();
  armedPromptTimer = setTimeout(() => {
    if (!convMode || vadSpeaking || busy) return;
    sendText('are you still there?', true);
    // No idle shutdown here — conv timeout (CONV_TIMEOUT_MS) handles final cleanup
  }, ARMED_PROMPT_MS);
}

function resetConvTimeout() {
  clearTimeout(convTimeoutTimer);
  convTimeoutTimer = setTimeout(() => {
    if (!convMode) return;
    if (busy) { resetConvTimeout(); return; }  // request in flight — extend
    stopConvMode();
  }, CONV_TIMEOUT_MS);
}

function vadLoop() {
  if (!convMode) return;
  vadRafId = requestAnimationFrame(vadLoop);
  if (busy || state === 'speaking') return;  // don't capture while assistant is talking

  const rms = computeRMS(vadAnalyser);

  if (!vadSpeaking) {
    if (rms > VAD_RMS_THRESHOLD) {
      if (vadSpeechStart === 0) vadSpeechStart = Date.now();
      if (Date.now() - vadSpeechStart >= VAD_START_DEBOUNCE_MS) {
        startVADRecording();
      }
    } else {
      vadSpeechStart = 0;
    }
  } else {
    if (rms < VAD_RMS_THRESHOLD) {
      if (vadSilenceStart === 0) vadSilenceStart = Date.now();
      if (Date.now() - vadSilenceStart >= VAD_STOP_DEBOUNCE_MS) {
        stopVADRecording();
      }
    } else {
      vadSilenceStart = 0;
    }
  }
}

function startVADRecording() {
  vadSpeaking     = true;
  vadSilenceStart = 0;
  vadSpeechStart  = 0;
  vadChunks       = [];

  resetArmedTimers();
  resetConvTimeout();

  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', '']
    .find(m => !m || MediaRecorder.isTypeSupported(m));
  vadMediaRec = new MediaRecorder(vadStream, mime ? { mimeType: mime } : {});
  vadMediaRec.ondataavailable = e => { if (e.data.size) vadChunks.push(e.data); };
  vadMediaRec.onstop = () => {
    vadSpeaking     = false;
    vadSpeechStart  = 0;
    vadSilenceStart = 0;
    const blob = new Blob(vadChunks, { type: vadMediaRec.mimeType });
    if (convMode) setState('armed');
    if (blob.size > 1000) sendVoiceBlob(blob);
    else if (convMode) startArmedTimers();
  };
  vadMediaRec.start();
  setState('listening');
}

function stopVADRecording() {
  if (vadMediaRec && vadMediaRec.state !== 'inactive') {
    vadMediaRec.stop();
  }
}

async function startConvMode() {
  try {
    vadStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    setState('error', 'Mic access denied');
    setTimeout(() => setState('idle'), 3000);
    return;
  }
  const ctx = getAudioCtx();
  if (ctx.state === 'suspended') await ctx.resume();
  const source = ctx.createMediaStreamSource(vadStream);
  vadAnalyser = ctx.createAnalyser();
  vadAnalyser.fftSize = 2048;
  source.connect(vadAnalyser);

  convMode = true;
  convBtn.classList.add('active');
  convLabel.textContent = 'End conversation';
  setState('armed');
  startArmedTimers();
  resetConvTimeout();
  vadLoop();
}

function stopConvMode() {
  convMode = false;
  cancelAnimationFrame(vadRafId);
  resetArmedTimers();
  clearTimeout(convTimeoutTimer);

  if (vadMediaRec && vadMediaRec.state !== 'inactive') vadMediaRec.stop();
  if (vadStream) vadStream.getTracks().forEach(t => t.stop());
  vadStream   = null;
  vadAnalyser = null;

  convBtn.classList.remove('active');
  convLabel.textContent = 'Start conversation';
  setState('idle');
}

convBtn.addEventListener('click', () => {
  if (convMode) stopConvMode();
  else startConvMode();
});

// ============================================================
// State machine
// ============================================================

const LABELS = {
  idle:      'Hold Space or tap to speak',
  armed:     'Listening for you…',
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

  const locked = s === 'thinking' || s === 'speaking';
  textInput.disabled = locked;
  sendBtn.disabled   = locked;

  if (s === 'armed' && convMode) {
    startArmedTimers();
  }
}

// ============================================================
// Disappearing captions
// ============================================================

const CAPTION_LINGER_MS = 3500; // how long caption stays after audio ends

function showCaption(text) {
  clearTimeout(captionFadeTimer);

  // Remove existing caption instantly if present
  if (captionEl) {
    captionEl.remove();
    captionEl = null;
  }

  const el = document.createElement('span');
  el.className = 'caption-text';
  el.textContent = text;
  captionBox.appendChild(el);
  captionEl = el;

  // Trigger fade-in on next frame
  requestAnimationFrame(() => {
    requestAnimationFrame(() => el.classList.add('visible'));
  });
}

function fadeCaption() {
  if (!captionEl) return;
  captionFadeTimer = setTimeout(() => {
    if (!captionEl) return;
    captionEl.classList.remove('visible');
    captionEl.classList.add('fading');
    const el = captionEl;
    captionEl = null;
    setTimeout(() => el.remove(), 700);
  }, CAPTION_LINGER_MS);
}

// ============================================================
// Order confirmation bar
// ============================================================

const ORDER_TIMEOUT = 15000;

function showOrderBar(orderSummary) {
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

  orderBarTimer.style.transition = 'none';
  orderBarTimer.style.transform = 'scaleX(1)';
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

async function handleResponse(data) {
  if (data.confirmation_required && data.order_summary) {
    showOrderBar(data.order_summary);
  }

  setState('speaking');
  if (data.reply) showCaption(data.reply);
  await playBase64Audio(data.audio_b64);
  fadeCaption();

  if (convMode) {
    resetConvTimeout();   // reset 120s window after every exchange
    setState('armed');
  } else {
    setState('idle');
  }
}

async function sendVoiceBlob(blob) {
  busy = true;
  setState('thinking');
  try {
    const form = new FormData();
    form.append('file', blob, 'audio.webm');
    const res = await fetch('/api/voice', { method: 'POST', body: form, headers: apiHeaders() });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    await handleResponse(data);
  } catch (e) {
    console.error(e);
    setState('error', e.message);
    setTimeout(() => convMode ? setState('armed') : setState('idle'), 3000);
  } finally {
    busy = false;
    if (convMode) startArmedTimers();
  }
}

async function sendText(text, silent = false) {
  if (!text.trim() || busy) return;

  // Silent pings ("are you still there?") must not block VAD —
  // fire in the background without locking the UI or setting busy.
  if (silent) {
    fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiHeaders() },
      body: JSON.stringify({ text }),
    }).then(r => r.ok ? r.json() : null).then(data => {
      if (data && convMode) handleResponse(data);
    }).catch(() => {});
    return;
  }

  busy = true;
  setState('thinking');
  try {
    const res = await fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiHeaders() },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    await handleResponse(data);
  } catch (e) {
    console.error(e);
    setState('error', e.message);
    setTimeout(() => convMode ? setState('armed') : setState('idle'), 3000);
  } finally {
    busy = false;
    if (convMode) startArmedTimers();
  }
}

// ============================================================
// MediaRecorder (PTT — Space bar)
// ============================================================

async function startRecording() {
  if (busy || state === 'listening' || convMode) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    setState('error', 'Mic access denied');
    setTimeout(() => setState('idle'), 3000);
    return;
  }
  audioChunks = [];
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', '']
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

document.addEventListener('keydown', e => {
  if (e.code === 'Space' && document.activeElement === document.body && !e.repeat) {
    e.preventDefault();
    startRecording();
  }
});
document.addEventListener('keyup', e => { if (e.code === 'Space') stopRecording(); });

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

document.addEventListener('pointerdown', () => getAudioCtx().resume(), { once: true });
