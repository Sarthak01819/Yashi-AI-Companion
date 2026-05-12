/**
 * Yashi Frontend Application
 * Manages WebSocket chat, UI state, audio playback, waveform visualisation.
 */

const App = (() => {
  // ── State ────────────────────────────────────────────────────
  let ws = null;
  let clientId = null;
  let isConnected = false;
  let isThinking = false;
  let currentBubble = null;       // streaming message element
  let currentAudioSource = null;  // Web Audio source for TTS
  let audioCtx = null;

  const RECONNECT_DELAY = 3000;
  let reconnectAttempts = 0;

  // ── DOM refs ─────────────────────────────────────────────────
  const chatArea     = document.getElementById('chat-area');
  const textInput    = document.getElementById('text-input');
  const sendBtn      = document.getElementById('send-btn');
  const micBtn       = document.getElementById('mic-btn');
  const statusDot    = document.getElementById('status-dot');
  const statusText   = document.getElementById('status-text');
  const emotionBadge = document.getElementById('emotion-badge');
  const modeChip     = document.getElementById('mode-chip');
  const waveform     = document.getElementById('waveform');
  const avatarRing   = document.getElementById('avatar-ring');
  const memBtn       = document.getElementById('mem-btn');
  const newSessBtn   = document.getElementById('new-session-btn');
  const memPanel     = document.getElementById('memory-panel');
  const memClose     = document.getElementById('mem-close');
  const memList      = document.getElementById('mem-list');
  const avatarCanvas = document.getElementById('avatar-canvas');

  // ── Init ─────────────────────────────────────────────────────
  function init() {
    clientId = 'client_' + Math.random().toString(36).slice(2);
    AvatarSystem.init(avatarCanvas);
    buildWaveform();
    connect();
    bindEvents();
    healthCheck();
  }

  function buildWaveform() {
    for (let i = 0; i < 24; i++) {
      const bar = document.createElement('div');
      bar.className = 'wave-bar';
      bar.id = 'wb' + i;
      waveform.appendChild(bar);
    }
  }

  // ── WebSocket ─────────────────────────────────────────────────
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url   = `${proto}://${location.host}/ws/chat/${clientId}`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      isConnected = true;
      reconnectAttempts = 0;
      setStatus('online', 'Connected');
      appendSystem('Yashi is ready. Say hello ✦');
    };

    ws.onclose = () => {
      isConnected = false;
      setStatus('offline', 'Reconnecting…');
      setTimeout(() => {
        reconnectAttempts++;
        connect();
      }, Math.min(RECONNECT_DELAY * reconnectAttempts, 15000));
    };

    ws.onerror = (e) => {
      console.error('WS error', e);
    };

    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      handleEvent(data);
    };
  }

  function send(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  // ── Event handling ────────────────────────────────────────────
  function handleEvent(data) {
    switch (data.type) {
      case 'emotion':
        updateEmotion(data);
        break;

      case 'thinking':
        if (!isThinking) {
          isThinking = true;
          showTypingIndicator(data.mode);
          updateModeChip(data.mode);
        }
        break;

      case 'token':
        appendToken(data.text);
        break;

      case 'done':
        finishMessage(data);
        break;

      case 'safety':
        appendSafetyNote(data.note);
        break;

      case 'plugin_result':
        appendSystem('🔧 ' + data.message);
        break;

      case 'session_id':
        appendSystem('New session started.');
        break;

      case 'reflection':
        if (data.summary) console.log('[Reflection]', data.summary);
        break;
    }
  }

  // ── UI: Messages ──────────────────────────────────────────────
  function appendUser(text) {
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerHTML = `
      <div class="msg-bubble">${escapeHtml(text)}</div>
      <div class="msg-meta">${timeNow()}</div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
  }

  function showTypingIndicator(mode) {
    removeTypingIndicator();
    const div = document.createElement('div');
    div.className = 'message yashi';
    div.id = 'typing-indicator';
    div.innerHTML = `
      <div class="msg-bubble">
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  function appendToken(token) {
    removeTypingIndicator();
    if (!currentBubble) {
      const div = document.createElement('div');
      div.className = 'message yashi';
      div.innerHTML = `<div class="msg-bubble" id="streaming-bubble"></div>`;
      chatArea.appendChild(div);
      currentBubble = document.getElementById('streaming-bubble');
    }
    currentBubble.textContent += token;
    scrollToBottom();
  }

  function finishMessage(data) {
    isThinking = false;
    currentBubble = null;

    // Add emotion + time meta under the last yashi message
    const last = chatArea.querySelector('.message.yashi:last-child');
    if (last) {
      const meta = document.createElement('div');
      meta.className = 'msg-meta';
      meta.innerHTML = `
        ${timeNow()}
        <span class="msg-emotion">${data.emotion || 'neutral'} · ${data.mode || ''} · ${data.elapsed}s</span>
      `;
      last.appendChild(meta);
    }

    // Avatar speaking animation
    if (data.audio_path) {
      playAudio(data.audio_path, data.full_text);
    }

    scrollToBottom();
  }

  function appendSafetyNote(note) {
    const div = document.createElement('div');
    div.className = 'message system';
    div.innerHTML = `<div class="msg-bubble">💛 ${escapeHtml(note)}</div>`;
    chatArea.appendChild(div);
    scrollToBottom();
  }

  function appendSystem(text) {
    const div = document.createElement('div');
    div.className = 'message system';
    div.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
    chatArea.appendChild(div);
    scrollToBottom();
  }

  // ── Audio playback ────────────────────────────────────────────
  async function playAudio(audioPath, text) {
    try {
      const filename = audioPath.split('/').pop();
      const url = `/api/audio/${filename}`;
      const resp = await fetch(url);
      if (!resp.ok) return;

      const buffer = await resp.arrayBuffer();
      if (!audioCtx) audioCtx = new AudioContext();

      const decoded = await audioCtx.decodeAudioData(buffer);
      const source  = audioCtx.createBufferSource();
      source.buffer = decoded;
      source.connect(audioCtx.destination);

      // Lip sync via amplitude estimation from text length
      const duration = decoded.duration;
      const words = text.split(' ').length;
      startLipSync(duration, words);

      source.start();
      currentAudioSource = source;
      avatarRing.classList.add('speaking');
      source.onended = () => {
        avatarRing.classList.remove('speaking');
        AvatarSystem.setSpeaking(false);
        currentAudioSource = null;
      };
    } catch (e) {
      console.warn('Audio playback error:', e);
    }
  }

  function startLipSync(duration, wordCount) {
    const intervalMs = (duration * 1000) / (wordCount * 4);
    let phase = 0;
    AvatarSystem.setSpeaking(true, 0.5);

    const interval = setInterval(() => {
      phase += 0.4;
      const amp = 0.3 + Math.abs(Math.sin(phase)) * 0.5;
      AvatarSystem.setSpeaking(true, amp);
    }, intervalMs);

    setTimeout(() => {
      clearInterval(interval);
      AvatarSystem.setSpeaking(false);
    }, duration * 1000);
  }

  // ── Emotion updates ───────────────────────────────────────────
  function updateEmotion(data) {
    const emotion = data.current_emotion || 'neutral';
    AvatarSystem.setEmotion(emotion);
    emotionBadge.textContent = emotion;
    emotionBadge.style.color = getEmotionColor(emotion);
  }

  function updateModeChip(mode) {
    const labels = { light: '⚡ Light', standard: '💬 Standard', deep: '🌊 Deep', support: '💛 Support' };
    modeChip.textContent = labels[mode] || mode;
  }

  function getEmotionColor(emotion) {
    const map = {
      happy: '#f5a623', joyful: '#ffc147', content: '#5ecfb0',
      neutral: '#4ecdc4', sad: '#7aa4d4', distressed: '#e8698a',
      concerned: '#9b8fcf', excited: '#ffd54f',
    };
    return map[emotion] || '#4ecdc4';
  }

  // ── Waveform (mic energy visualiser) ─────────────────────────
  let waveAnimFrame = null;
  let waveEnergy = 0;

  function updateWaveform(energy) {
    waveEnergy = energy;
    if (!waveform.classList.contains('active')) {
      waveform.classList.add('active');
    }
  }

  function animateWaveform() {
    const bars = waveform.querySelectorAll('.wave-bar');
    bars.forEach((bar, i) => {
      const noise = Math.random() * 0.6 + 0.4;
      const sineOffset = Math.sin(Date.now() * 0.005 + i * 0.5) * 0.3 + 0.7;
      const h = Math.max(3, waveEnergy * 90 * noise * sineOffset);
      bar.style.height = h + 'px';
      bar.style.opacity = 0.4 + waveEnergy * 1.5;
    });
    waveAnimFrame = requestAnimationFrame(animateWaveform);
  }

  // ── Voice input ───────────────────────────────────────────────
  let voiceMode = false;

  micBtn.addEventListener('click', async () => {
    if (!voiceMode) {
      try {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url   = `${proto}://${location.host}/ws/voice/${clientId}_voice`;

        await VoiceSystem.start(
          url,
          (text) => {
            if (text.trim()) {
              appendUser(text);
              send({ type: 'text', text });
            }
          },
          (energy) => updateWaveform(energy)
        );

        voiceMode = true;
        micBtn.classList.add('recording');
        micBtn.title = 'Stop recording';
        waveform.classList.add('active');
        animateWaveform();
      } catch (e) {
        appendSystem('Microphone access denied or unavailable.');
      }
    } else {
      VoiceSystem.stop();
      voiceMode = false;
      micBtn.classList.remove('recording');
      micBtn.title = 'Start voice input';
      waveform.classList.remove('active');
      cancelAnimationFrame(waveAnimFrame);
    }
  });

  // ── Text input / send ─────────────────────────────────────────
  function bindEvents() {
    sendBtn.addEventListener('click', sendText);
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendText();
      }
    });

    textInput.addEventListener('input', () => {
      textInput.style.height = 'auto';
      textInput.style.height = Math.min(textInput.scrollHeight, 160) + 'px';
      sendBtn.disabled = !textInput.value.trim();
    });

    newSessBtn.addEventListener('click', () => {
      send({ type: 'new_session' });
      chatArea.innerHTML = '';
      appendSystem('New conversation started.');
    });

    memBtn.addEventListener('click', openMemoryPanel);
    memClose.addEventListener('click', () => memPanel.classList.remove('open'));
    memPanel.addEventListener('click', (e) => {
      if (e.target === memPanel) memPanel.classList.remove('open');
    });
  }

  function sendText() {
    const text = textInput.value.trim();
    if (!text || !isConnected) return;

    appendUser(text);
    send({ type: 'text', text });
    textInput.value = '';
    textInput.style.height = 'auto';
    sendBtn.disabled = true;
  }

  // ── Memory panel ──────────────────────────────────────────────
  async function openMemoryPanel() {
    memPanel.classList.add('open');
    memList.innerHTML = '<div style="color:var(--text-muted);font-size:13px">Loading…</div>';

    try {
      const [factsResp, reflResp] = await Promise.all([
        fetch('/api/facts'),
        fetch('/api/reflections?limit=5'),
      ]);
      const facts = await factsResp.json();
      const refl  = await reflResp.json();

      memList.innerHTML = '';

      if (facts.facts.length) {
        const h = document.createElement('div');
        h.style.cssText = 'font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin:0 0 8px';
        h.textContent = 'About You';
        memList.appendChild(h);

        facts.facts.forEach(f => {
          const el = document.createElement('div');
          el.className = 'memory-item';
          el.textContent = `${f.category}: ${f.fact}`;
          memList.appendChild(el);
        });
      }

      if (refl.reflections.length) {
        const h = document.createElement('div');
        h.style.cssText = 'font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin:16px 0 8px';
        h.textContent = 'Recent Reflections';
        memList.appendChild(h);

        refl.reflections.forEach(r => {
          const el = document.createElement('div');
          el.className = 'memory-item';
          el.innerHTML = `<strong style="color:var(--accent);font-size:12px">${r.mood_trend || 'neutral'}</strong><br>${r.summary}`;
          memList.appendChild(el);
        });
      }

      if (!facts.facts.length && !refl.reflections.length) {
        memList.innerHTML = '<div class="memory-item">No memories yet — keep chatting!</div>';
      }
    } catch (e) {
      memList.innerHTML = '<div class="memory-item" style="color:var(--rose)">Could not load memories.</div>';
    }
  }

  // ── Status ────────────────────────────────────────────────────
  function setStatus(state, text) {
    statusDot.className = `status-dot ${state}`;
    statusText.textContent = text;
  }

  async function healthCheck() {
    try {
      const r = await fetch('/api/health');
      const d = await r.json();
      if (!d.ollama) appendSystem('⚠️ Ollama is not running. Start it with: ollama serve');
      if (d.models && d.models.length === 0) appendSystem('⚠️ No Ollama models found. Run: ollama pull mistral');
    } catch (e) {}
  }

  // ── Helpers ───────────────────────────────────────────────────
  function scrollToBottom() {
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', App.init);
