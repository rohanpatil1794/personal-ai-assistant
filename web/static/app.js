/* Ronny — Voice-first minimalist UI */

const sphere          = document.getElementById('sphere');
const statusDot       = document.getElementById('status-dot');
const statusLabel     = document.getElementById('status-label');
const waveform        = document.getElementById('waveform');
const pttBtn          = document.getElementById('ptt-btn');
const pttLabel        = document.getElementById('ptt-label');
const textInput       = document.getElementById('text-input');
const sendBtn         = document.getElementById('send-btn');
const emptyState      = document.getElementById('empty-state');
const messagesEl      = document.getElementById('messages');
const clearBtn        = document.getElementById('clear-btn');
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
let thinkingEl = null;
let orderDismissTimer = null;

// ============================================================
// VAD / Conversation mode
// ============================================================

const VAD_RMS_THRESHOLD     = 0.012; // tune for ambient noise
const VAD_START_DEBOUNCE_MS = 200;   // must be above threshold this long to start
const VAD_STOP_DEBOUNCE_MS  = 1200;  // must be below threshold this long to stop
const CONV_TIMEOUT_MS       = 30000; // end conv mode after 30s total silence
const ARMED_PROMPT_MS       = 5000;  // after 5s in armed state, ask "are you there?"
const ARMED_IDLE_MS         = 5000;  // 5s after prompt with no reply → exit conv mode

let convMode        = false;
let vadStream       = null;    // kept alive for full session
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
    sendText('are you still there?', true); // silent — don't show in chat
    armedIdleTimer = setTimeout(() => {
      if (convMode && !vadSpeaking && !busy) stopConvMode();
    }, ARMED_IDLE_MS);
  }, ARMED_PROMPT_MS);
}

function resetConvTimeout() {
  clearTimeout(convTimeoutTimer);
  convTimeoutTimer = setTimeout(() => {
    if (convMode) stopConvMode();
  }, CONV_TIMEOUT_MS);
}

function vadLoop() {
  if (!convMode) return;
  vadRafId = requestAnimationFrame(vadLoop);
  if (busy) return;

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

  if (!convMode) {
    if (s === 'listening') {
      pttBtn.classList.add('listening');
      pttLabel.textContent = 'Release to send';
    } else {
      pttBtn.classList.remove('listening');
      pttLabel.textContent = 'Hold to talk';
    }
  }

  const locked = s === 'thinking' || s === 'speaking';
  textInput.disabled = locked;
  sendBtn.disabled   = locked;

  if (s === 'thinking') {
    showThinking();
  } else {
    hideThinking();
  }

  // Restart inactivity timers whenever we go armed
  if (s === 'armed' && convMode) {
    startArmedTimers();
  }
}

// ============================================================
// Conversation history
// ============================================================

function appendMessage(role, text) {
  emptyState.classList.add('hidden');
  clearBtn.classList.add('visible');

  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function showThinking() {
  if (thinkingEl) return;
  thinkingEl = document.createElement('div');
  thinkingEl.className = 'msg msg-assistant msg-thinking';
  thinkingEl.innerHTML =
    '<span class="thinking-dot"></span>' +
    '<span class="thinking-dot"></span>' +
    '<span class="thinking-dot"></span>';
  messagesEl.appendChild(thinkingEl);
  scrollToBottom();
}

function hideThinking() {
  if (thinkingEl) {
    thinkingEl.remove();
    thinkingEl = null;
  }
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

clearBtn.addEventListener('click', () => {
  messagesEl.innerHTML = '';
  emptyState.classList.remove('hidden');
  clearBtn.classList.remove('visible');
});

// ============================================================
// Order confirmation bar — slides up, auto-dismisses in 15s
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
  orderBarTimer.getBoundingClientRect(); // force reflow
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

async function handleResponse(data, transcriptText) {
  if (transcriptText) appendMessage('user', transcriptText);

  if (data.confirmation_required && data.order_summary) {
    showOrderBar(data.order_summary);
  }

  setState('speaking');
  if (data.reply) appendMessage('assistant', data.reply);
  await playBase64Audio(data.audio_b64);

  if (convMode) {
    setState('armed'); // re-arm VAD — RAF loop already running
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
    const res = await fetch('/api/voice', { method: 'POST', body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    await handleResponse(data, data.transcript);
  } catch (e) {
    console.error(e);
    setState('error', e.message);
    setTimeout(() => convMode ? setState('armed') : setState('idle'), 3000);
  } finally {
    busy = false;
    if (convMode) startArmedTimers();
  }
}

// silent: true → don't show user message (used for internal "are you there?" probe)
async function sendText(text, silent = false) {
  if (!text.trim() || busy) return;
  busy = true;

  const isSentinel = text === '__confirm_order__' || text === 'cancel the order' || silent;
  if (!isSentinel) appendMessage('user', text);

  setState('thinking');
  try {
    const res = await fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    await handleResponse(data, null);
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
// MediaRecorder (PTT — fallback mode)
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

pttBtn.addEventListener('mousedown',  e => { e.preventDefault(); startRecording(); });
pttBtn.addEventListener('mouseup',    () => stopRecording());
pttBtn.addEventListener('mouseleave', () => stopRecording());
pttBtn.addEventListener('touchstart', e => { e.preventDefault(); startRecording(); }, { passive: false });
pttBtn.addEventListener('touchend',   e => { e.preventDefault(); stopRecording(); },  { passive: false });

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
