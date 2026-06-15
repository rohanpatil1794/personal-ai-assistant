/* Ronny web UI — state machine + MediaRecorder + AudioContext */

const sphere      = document.getElementById('sphere');
const statusLabel = document.getElementById('status-label');
const messages    = document.getElementById('messages');
const chatPanel   = document.getElementById('chat-panel');
const pttBtn      = document.getElementById('ptt-btn');
const textInput   = document.getElementById('text-input');
const sendBtn     = document.getElementById('send-btn');

// States: idle | listening | thinking | speaking | error
let state = 'idle';
let mediaRecorder = null;
let audioChunks = [];
let audioCtx = null;
let busy = false;

function setState(s, label) {
  state = s;
  sphere.className = s;
  statusLabel.textContent = label ?? {
    idle:      'Hold Space or tap to speak',
    listening: 'Listening…',
    thinking:  'Thinking…',
    speaking:  'Speaking…',
    error:     'Something went wrong',
  }[s] ?? s;
}

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `<span class="role">${role === 'user' ? 'You' : 'Ronny'}:</span><span class="body">${escHtml(text)}</span>`;
  messages.appendChild(div);
  chatPanel.scrollTop = chatPanel.scrollHeight;
}

function escHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// --- Audio playback via Web Audio API ---
function getAudioCtx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return audioCtx;
}

async function playBase64Audio(b64) {
  const ctx = getAudioCtx();
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

// --- Core send logic ---
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
    const data = await res.json();
    if (data.transcript) addMessage('user', data.transcript);
    addMessage('assistant', data.reply);
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

async function sendText(text) {
  if (!text.trim() || busy) return;
  busy = true;
  addMessage('user', text);
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

// --- MediaRecorder helpers ---
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
  // Prefer WebM/Opus; fall back to whatever browser supports
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
  pttBtn.classList.add('listening');
  pttBtn.textContent = '🎙 Release to Send';
}

function stopRecording() {
  if (state !== 'listening' || !mediaRecorder) return;
  mediaRecorder.stop();
  pttBtn.classList.remove('listening');
  pttBtn.textContent = '🎤 Hold to Talk';
}

// --- PTT button ---
pttBtn.addEventListener('mousedown', e => { e.preventDefault(); startRecording(); });
pttBtn.addEventListener('mouseup',   () => stopRecording());
pttBtn.addEventListener('mouseleave',() => stopRecording());
pttBtn.addEventListener('touchstart', e => { e.preventDefault(); startRecording(); }, { passive: false });
pttBtn.addEventListener('touchend',   e => { e.preventDefault(); stopRecording(); }, { passive: false });

// --- Spacebar PTT ---
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && e.target === document.body && !e.repeat) {
    e.preventDefault();
    startRecording();
  }
});
document.addEventListener('keyup', e => {
  if (e.code === 'Space') stopRecording();
});

// --- Text input ---
sendBtn.addEventListener('click', () => {
  const t = textInput.value;
  textInput.value = '';
  sendText(t);
});
textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    const t = textInput.value;
    textInput.value = '';
    sendText(t);
  }
});

// Resume AudioContext on first user gesture (required by Chrome autoplay policy)
document.addEventListener('click', () => getAudioCtx().resume(), { once: true });
