/* Ronny — JARVIS-Style Voice-First UI */

// ============================================================
// Background canvas — dot grid + Jarvis particles
// ============================================================

(function initBgCanvas() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    buildGrid();
  }

  let gridOff = null;
  function buildGrid() {
    gridOff = document.createElement('canvas');
    gridOff.width  = canvas.width;
    gridOff.height = canvas.height;
    const gc = gridOff.getContext('2d');
    gc.fillStyle = 'rgba(0,212,255,0.055)';
    const G = 40;
    for (let x = 0; x <= gridOff.width; x += G) {
      for (let y = 0; y <= gridOff.height; y += G) {
        gc.beginPath();
        gc.arc(x, y, 0.8, 0, Math.PI * 2);
        gc.fill();
      }
    }
  }

  resize();
  window.addEventListener('resize', resize, { passive: true });

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const particles = Array.from({ length: 38 }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    r: Math.random() * 1.3 + 0.3,
    vy: -(Math.random() * 0.26 + 0.05),
    vx: (Math.random() - 0.5) * 0.08,
    alpha: Math.random() * 0.22 + 0.05,
    phase: Math.random() * Math.PI * 2,
    freq: Math.random() * 0.011 + 0.004,
    col: Math.random() > 0.78 ? '#39ff14' : '#00d4ff',
  }));

  (function loop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (gridOff) ctx.drawImage(gridOff, 0, 0);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy; p.phase += p.freq;
      if (p.y < -10) { p.y = canvas.height + 10; p.x = Math.random() * canvas.width; }
      const a = p.alpha * (0.5 + 0.5 * Math.sin(p.phase));
      ctx.save();
      ctx.globalAlpha = a;
      ctx.shadowBlur  = 8;
      ctx.shadowColor = p.col;
      ctx.fillStyle   = p.col;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
    requestAnimationFrame(loop);
  })();
})();

// ============================================================
// Circuit canvas — PCB traces + signal pulses from sphere
// ============================================================

(function initCircuits() {
  const canvas = document.getElementById('circuit-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const GRID = 16;
  let traces    = [];
  let offscreen = null;

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function getSphereCenter() {
    const el = document.getElementById('sphere');
    if (!el) return { x: window.innerWidth / 2, y: window.innerHeight * 0.46 };
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }

  class Trace {
    constructor(sx, sy, startAngle) {
      this.segments = [];
      this.vias     = [];
      this.pads     = [];
      this.pulses   = [];
      this.totalLen = 0;
      this.isGreen  = Math.random() < 0.18;
      this.speedMul = 1;
      this._build(sx, sy, startAngle);
      const n = Math.floor(Math.random() * 2) + 1;
      for (let i = 0; i < n; i++) {
        this.pulses.push({
          t:       Math.random(),
          speed:   0.0032 + Math.random() * 0.004,
          isGreen: this.isGreen || Math.random() < 0.12,
        });
      }
    }

    _build(sx, sy, startAngle) {
      const DIRS = [[1,0],[0,1],[-1,0],[0,-1]];
      let dir = Math.round(startAngle / 90) % 4;
      if (dir < 0) dir += 4;
      let cx = sx, cy = sy;
      const numSegs = Math.floor(Math.random() * 6) + 3;
      let travel = 0;
      const maxTravel = 260 + Math.random() * 280;

      for (let i = 0; i < numSegs && travel < maxTravel; i++) {
        const segLen = (Math.floor(Math.random() * 7) + 2) * GRID;
        const [dx, dy] = DIRS[dir];
        const nx = cx + dx * segLen;
        const ny = cy + dy * segLen;

        if (nx < -100 || nx > canvas.width + 100 || ny < -100 || ny > canvas.height + 100) break;

        this.segments.push({ x1: cx, y1: cy, x2: nx, y2: ny, len: segLen });
        this.totalLen += segLen;
        travel += segLen;

        if (i < numSegs - 1) {
          this.vias.push({ x: nx, y: ny });
        } else {
          this.pads.push({ x: nx, y: ny });
        }

        cx = nx; cy = ny;

        // random turn (bias toward continuing or 90° turns)
        const roll = Math.random();
        if (roll > 0.4) dir = (dir + (Math.random() > 0.5 ? 1 : 3)) % 4;
      }
    }

    getPoint(dist) {
      let rem = Math.max(0, Math.min(dist, this.totalLen));
      for (const s of this.segments) {
        if (rem <= s.len) {
          const t = rem / s.len;
          return { x: s.x1 + (s.x2 - s.x1) * t, y: s.y1 + (s.y2 - s.y1) * t };
        }
        rem -= s.len;
      }
      const last = this.segments[this.segments.length - 1];
      return last ? { x: last.x2, y: last.y2 } : { x: 0, y: 0 };
    }

    drawStatic(c) {
      if (!this.segments.length) return;
      const base = this.isGreen ? '57,255,20' : '0,212,255';

      // soft outer bloom
      c.save();
      c.strokeStyle = `rgba(${base},0.07)`;
      c.lineWidth   = 7;
      c.lineCap     = 'butt';
      c.beginPath();
      for (const s of this.segments) { c.moveTo(s.x1, s.y1); c.lineTo(s.x2, s.y2); }
      c.stroke();

      // main trace line
      c.strokeStyle = `rgba(${base},0.27)`;
      c.lineWidth   = 1.5;
      c.beginPath();
      for (const s of this.segments) { c.moveTo(s.x1, s.y1); c.lineTo(s.x2, s.y2); }
      c.stroke();
      c.restore();

      // via holes (junction circles)
      for (const v of this.vias) {
        c.save();
        c.fillStyle   = `rgba(${base},0.5)`;
        c.strokeStyle = `rgba(${base},0.35)`;
        c.lineWidth   = 1;
        c.beginPath(); c.arc(v.x, v.y, 2.5, 0, Math.PI * 2); c.fill();
        c.beginPath(); c.arc(v.x, v.y, 5.5, 0, Math.PI * 2); c.stroke();
        c.restore();
      }

      // SMD pad at endpoints
      for (const p of this.pads) {
        c.save();
        c.strokeStyle = `rgba(${base},0.42)`;
        c.fillStyle   = `rgba(${base},0.1)`;
        c.lineWidth   = 1;
        c.fillRect(p.x - 9, p.y - 6, 18, 12);
        c.strokeRect(p.x - 9, p.y - 6, 18, 12);
        // inner via
        c.fillStyle = `rgba(${base},0.45)`;
        c.beginPath(); c.arc(p.x, p.y, 2, 0, Math.PI * 2); c.fill();
        c.restore();
      }
    }

    tick() {
      for (const p of this.pulses) {
        p.t += p.speed * this.speedMul;
        if (p.t > 1) p.t = 0;
      }
      if (Math.random() < 0.0011 && this.pulses.length < 5) {
        this.pulses.push({
          t:       0,
          speed:   0.003 + Math.random() * 0.005,
          isGreen: this.isGreen || Math.random() < 0.14,
        });
      }
    }

    drawPulses(c) {
      if (!this.totalLen) return;
      for (const p of this.pulses) {
        const pos  = this.getPoint(p.t * this.totalLen);
        const col  = p.isGreen ? '#39ff14' : '#00d4ff';
        const prev = this.getPoint(Math.max(0, p.t * this.totalLen - 14));
        c.save();
        // trailing dot
        c.globalAlpha = 0.35;
        c.fillStyle   = col;
        c.shadowBlur  = 6;
        c.shadowColor = col;
        c.beginPath(); c.arc(prev.x, prev.y, 1.5, 0, Math.PI * 2); c.fill();
        // main bright dot
        c.globalAlpha = 0.95;
        c.fillStyle   = '#ffffff';
        c.shadowBlur  = 18;
        c.shadowColor = col;
        c.beginPath(); c.arc(pos.x, pos.y, 2.4, 0, Math.PI * 2); c.fill();
        c.restore();
      }
    }
  }

  function buildAll() {
    const c   = getSphereCenter();
    const SR  = 108;
    traces    = [];
    const N   = 22;
    for (let i = 0; i < N; i++) {
      const angle = (i / N) * 360 + Math.random() * (360 / N * 0.4);
      const rad   = angle * Math.PI / 180;
      const sx    = Math.round((c.x + Math.cos(rad) * SR) / GRID) * GRID;
      const sy    = Math.round((c.y + Math.sin(rad) * SR) / GRID) * GRID;
      traces.push(new Trace(sx, sy, angle));
    }
  }

  function renderStatic() {
    offscreen         = document.createElement('canvas');
    offscreen.width   = canvas.width;
    offscreen.height  = canvas.height;
    const oc          = offscreen.getContext('2d');
    traces.forEach(t  => t.drawStatic(oc));
  }

  function loop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (offscreen) ctx.drawImage(offscreen, 0, 0);
    traces.forEach(t => { t.tick(); t.drawPulses(ctx); });
    requestAnimationFrame(loop);
  }

  // Init after first paint so sphere position is available
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      resize();
      buildAll();
      renderStatic();
      loop();
    });
  });

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      resize();
      buildAll();
      renderStatic();
    }, 220);
  }, { passive: true });

  // Exposed so setState() can tune pulse speeds
  window._setCircuitState = function (s) {
    const speed = { idle: 1, armed: 1.1, listening: 1.6, thinking: 2.2, speaking: 2.0, error: 0.4 };
    const mul   = speed[s] ?? 1;
    traces.forEach(t => { t.speedMul = mul; });
  };
})();

// ============================================================
// Intro — JARVIS boot sequence
// ============================================================

(function initIntro() {
  const intro = document.getElementById('intro');
  if (!intro) return;

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    intro.classList.add('done');
    return;
  }

  const bootLines = [
    { id: 'boot-1', text: 'SYSTEM BOOT SEQUENCE INITIATED' },
    { id: 'boot-2', text: 'LOADING VOICE RECOGNITION PROTOCOLS' },
    { id: 'boot-3', text: 'CALIBRATING NEURAL INTERFACE' },
    { id: 'boot-4', text: 'ALL SYSTEMS NOMINAL' },
  ];

  const bar  = intro.querySelector('.intro-progress-bar');
  const pct  = intro.querySelector('.intro-progress-pct');

  // Reveal boot lines one by one
  bootLines.forEach((l, i) => {
    setTimeout(() => {
      const el = document.getElementById(l.id);
      if (el) { el.textContent = '> ' + l.text; el.classList.add('active'); }
    }, 180 + i * 370);
  });

  // Fill progress bar
  let progress = 0;
  const interval = setInterval(() => {
    progress = Math.min(100, progress + Math.random() * 5.5 + 1.5);
    if (bar) bar.style.width = progress + '%';
    if (pct) pct.textContent = Math.floor(progress) + '%';
    if (progress >= 100) {
      clearInterval(interval);
      setTimeout(() => {
        intro.classList.add('phase2');
        setTimeout(dismiss, 2600);
      }, 280);
    }
  }, 75);

  function dismiss() {
    intro.classList.add('done');
  }

  intro.addEventListener('click', () => { clearInterval(interval); dismiss(); }, { once: true });

  function handleKeyDismiss(e) {
    if (e.key === ' ') return; // Space is for PTT; ignore during intro
    document.removeEventListener('keydown', handleKeyDismiss);
    clearInterval(interval);
    dismiss();
  }
  document.addEventListener('keydown', handleKeyDismiss);
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
    setState('error', 'MIC ACCESS DENIED');
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
  idle:      'STANDBY // HOLD SPACE TO SPEAK',
  armed:     'VOICE DETECTION ACTIVE',
  listening: 'CAPTURING AUDIO INPUT...',
  thinking:  'PROCESSING REQUEST...',
  speaking:  'AUDIO OUTPUT ACTIVE',
  error:     'SYSTEM ERROR',
};

function setState(s, customLabel) {
  state = s;
  sphere.className    = s;
  statusDot.className = `status-dot ${s}`;
  statusLabel.textContent = customLabel ?? LABELS[s] ?? s;
  waveform.classList.toggle('active', s === 'listening');

  const locked = s === 'thinking' || s === 'speaking';
  textInput.disabled = locked;
  sendBtn.disabled   = locked;

  // Tune circuit pulse speeds
  if (window._setCircuitState) window._setCircuitState(s);
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
  orderBarTimer.style.transform  = 'scaleX(1)';
  orderBarTimer.getBoundingClientRect();
  orderBarTimer.style.transition = `transform ${ORDER_TIMEOUT}ms linear`;
  orderBarTimer.style.transform  = 'scaleX(0)';

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
  orderBarTimer.style.transform  = 'scaleX(0)';
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
  const bytes  = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const buffer = await ctx.decodeAudioData(bytes.buffer);
  return new Promise(resolve => {
    const src = ctx.createBufferSource();
    src.buffer  = buffer;
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

  if (convMode) setState('armed');
  else          setState('idle');
}

async function sendVoiceBlob(blob) {
  busy = true;
  setState('thinking');
  try {
    const form = new FormData();
    form.append('file', blob, 'audio.webm');
    const res  = await fetch('/api/voice', { method: 'POST', body: form });
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
    const res  = await fetch('/api/text', {
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
    setState('error', 'MIC ACCESS DENIED');
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
