/* Ronny — Voice-first minimalist UI */

// ============================================================
// Background particle system (canvas — always running)
// ============================================================

(function initParticles() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const COLORS = ['#4f8ef7', '#67e8f9', '#a5b4fc', '#e0e7ff', '#fff'];
  const WEIGHTS = [0.3, 0.2, 0.2, 0.15, 0.15]; // probability weight per color
  const COUNT = 75;

  function pickColor() {
    let r = Math.random(), acc = 0;
    for (let i = 0; i < WEIGHTS.length; i++) {
      acc += WEIGHTS[i];
      if (r < acc) return COLORS[i];
    }
    return COLORS[0];
  }

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize, { passive: true });

  class Particle {
    constructor(born) {
      this.reset(born);
    }
    reset(born) {
      this.x     = Math.random() * canvas.width;
      this.y     = born ? Math.random() * canvas.height : canvas.height + 8;
      this.r     = Math.random() * 1.6 + 0.4;
      this.vx    = (Math.random() - 0.5) * 0.25;
      this.vy    = -(Math.random() * 0.35 + 0.08);
      this.alpha = Math.random() * 0.45 + 0.1;
      this.phase = Math.random() * Math.PI * 2;
      this.freq  = Math.random() * 0.018 + 0.006;
      this.color = pickColor();
    }
    step() {
      this.x     += this.vx;
      this.y     += this.vy;
      this.phase += this.freq;
      if (this.y < -10 || this.x < -10 || this.x > canvas.width + 10) {
        this.reset(false);
      }
    }
    draw() {
      const a = this.alpha * (0.55 + 0.45 * Math.sin(this.phase));
      ctx.save();
      ctx.globalAlpha = a;
      ctx.shadowBlur  = this.r * 5;
      ctx.shadowColor = this.color;
      ctx.fillStyle   = this.color;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  const particles = Array.from({ length: COUNT }, () => new Particle(true));

  // Respect reduced-motion — stop loop but keep canvas transparent
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReduced) return;

  (function loop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => { p.step(); p.draw(); });
    requestAnimationFrame(loop);
  })();
})();

// ============================================================
// Intro sequence
// ============================================================

(function initIntro() {
  const intro = document.getElementById('intro');
  if (!intro) return;

  // Respect reduced-motion — skip intro entirely
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    intro.classList.add('done');
    return;
  }

  function dismiss() {
    intro.classList.add('done');
  }

  // Auto-dismiss after 3s
  const timer = setTimeout(dismiss, 3000);

  // Tap / keydown to skip
  intro.addEventListener('click', () => { clearTimeout(timer); dismiss(); }, { once: true });
  document.addEventListener('keydown', () => { clearTimeout(timer); dismiss(); }, { once: true });
})();

// ============================================================
// Main app
// ============================================================

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
const CONV_TIMEOUT_MS       = 60000;
const ARMED_PROMPT_MS       = 15000;
const ARMED_IDLE_MS         = 10000;

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
    resetArmedTimers();
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
}

// ============================================================
// Disappearing captions
// ============================================================

const CAPTION_LINGER_MS = 3500;

function showCaption(text) {
  clearTimeout(captionFadeTimer);
  if (captionEl) { captionEl.remove(); captionEl = null; }

  const el = document.createElement('span');
  el.className = 'caption-text';
  el.textContent = text;
  captionBox.appendChild(el);
  captionEl = el;

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
    const res = await fetch('/api/voice', { method: 'POST', body: form });
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
  busy = true;

  setState('thinking');
  try {
    const res = await fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
// PTT — Space bar
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
