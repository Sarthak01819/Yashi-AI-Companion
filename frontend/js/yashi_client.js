/**
 * Yashi WebSocket Client — main frontend logic.
 * Handles: WS connection, message rendering, audio playback, state management.
 */

const YashiClient = (() => {
  const WS_URL = `ws://${location.host}/ws/chat/`;
  let ws = null;
  let clientId = null;
  let sessionId = null;
  let currentResponse = '';
  let responseEl = null;
  let isConnected = false;

  // DOM refs (populated on init)
  let ui = {};

  function init() {
    ui = {
      chatLog:       document.getElementById('chat-log'),
      input:         document.getElementById('text-input'),
      sendBtn:       document.getElementById('send-btn'),
      micBtn:        document.getElementById('mic-btn'),
      statusDot:     document.getElementById('status-dot'),
      statusText:    document.getElementById('status-text'),
      emotionBadge:  document.getElementById('emotion-badge'),
      modeBadge:     document.getElementById('mode-badge'),
      typingIndicator: document.getElementById('typing-indicator'),
      newSessionBtn: document.getElementById('new-session-btn'),
    };

    clientId = 'client_' + Math.random().toString(36).slice(2, 10);
    connect();

    ui.sendBtn?.addEventListener('click', sendText);
    ui.input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); }
    });
    ui.newSessionBtn?.addEventListener('click', newSession);

    // Auto-resize textarea
    ui.input?.addEventListener('input', () => {
      ui.input.style.height = 'auto';
      ui.input.style.height = Math.min(ui.input.scrollHeight, 160) + 'px';
    });
  }

  function connect() {
    setStatus('connecting', 'Connecting...');
    ws = new WebSocket(WS_URL + clientId);

    ws.onopen = () => {
      isConnected = true;
      setStatus('connected', 'Connected');
    };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      handleEvent(data);
    };

    ws.onclose = () => {
      isConnected = false;
      setStatus('disconnected', 'Disconnected — reconnecting...');
      setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      setStatus('error', 'Connection error');
    };
  }

  function handleEvent(data) {
    switch (data.type) {
      case 'connected':
        sessionId = data.session;
        appendMessage('assistant', data.message, 'neutral');
        setStatus('connected', 'Ready');
        break;

      case 'emotion':
        updateEmotion(data.current_emotion, data.emotional_state);
        break;

      case 'thinking':
        setStatus('thinking', `Thinking (${data.mode})...`);
        updateMode(data.mode);
        showTyping(true);
        currentResponse = '';
        responseEl = createStreamingBubble();
        break;

      case 'token':
        if (responseEl) {
          currentResponse += data.text;
          responseEl.querySelector('.msg-content').textContent = currentResponse;
          scrollToBottom();
        }
        break;

      case 'done':
        showTyping(false);
        finalizeResponse(data);
        setStatus('connected', 'Ready');
        break;

      case 'safety':
        appendSafetyNote(data.note);
        break;

      case 'plugin_response':
        appendMessage('assistant', data.message, 'neutral', '🔌');
        break;

      case 'transcribed':
        if (ui.input) {
          ui.input.value = data.text;
          ui.input.dispatchEvent(new Event('input'));
        }
        appendMessage('user', data.text, 'neutral');
        ui.input.value = '';
        break;

      case 'listening':
        setStatus('listening', 'Listening...');
        break;

      case 'transcribing':
        setStatus('thinking', 'Transcribing...');
        break;

      case 'session_reset':
        sessionId = data.session;
        clearChat();
        appendMessage('assistant', "I've started a fresh conversation. What's on your mind?", 'neutral');
        break;

      case 'reflection':
        showReflectionToast(data.summary);
        break;
    }
  }

  function sendText() {
    const text = ui.input?.value?.trim();
    if (!text || !isConnected) return;

    appendMessage('user', text, 'neutral');
    ws.send(JSON.stringify({ type: 'text', text }));
    ui.input.value = '';
    ui.input.style.height = 'auto';
  }

  function newSession() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'new_session' }));
    }
  }

  function appendMessage(role, text, emotion, prefix = '') {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.dataset.emotion = emotion || 'neutral';

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (prefix) {
      const tag = document.createElement('span');
      tag.className = 'msg-prefix';
      tag.textContent = prefix + ' ';
      bubble.appendChild(tag);
    }

    const content = document.createElement('span');
    content.className = 'msg-content';
    content.textContent = text;
    bubble.appendChild(content);

    div.appendChild(bubble);
    ui.chatLog?.appendChild(div);
    scrollToBottom();
    return div;
  }

  function createStreamingBubble() {
    const div = document.createElement('div');
    div.className = 'message assistant streaming';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    const content = document.createElement('span');
    content.className = 'msg-content';
    bubble.appendChild(content);
    div.appendChild(bubble);
    ui.chatLog?.appendChild(div);
    scrollToBottom();
    return div;
  }

  function finalizeResponse(data) {
    if (responseEl) {
      responseEl.classList.remove('streaming');
      responseEl.dataset.emotion = data.emotion || 'neutral';
    }
    responseEl = null;

    // Play TTS audio if available
    if (data.audio_path) {
      const filename = data.audio_path.split(/[\\/]/).pop();
      playAudio(`/audio/tts/${filename}`);
    }

    // Update avatar
    if (window.YashiAvatar) {
      YashiAvatar.setEmotion(data.emotion || 'neutral');
      YashiAvatar.stopLipSync();
    }
  }

  function playAudio(url) {
    const audio = new Audio(url);
    if (window.YashiAvatar) YashiAvatar.startLipSync();
    audio.onended = () => { if (window.YashiAvatar) YashiAvatar.stopLipSync(); };
    audio.play().catch(e => console.warn('[Audio] Play failed:', e));
  }

  function appendSafetyNote(note) {
    const div = document.createElement('div');
    div.className = 'safety-note';
    div.textContent = '💙 ' + note;
    ui.chatLog?.appendChild(div);
    scrollToBottom();
  }

  function showReflectionToast(summary) {
    const toast = document.createElement('div');
    toast.className = 'reflection-toast';
    toast.textContent = '✨ ' + summary;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 50);
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 500); }, 5000);
  }

  function updateEmotion(emotion, state) {
    if (ui.emotionBadge) {
      ui.emotionBadge.textContent = emotion;
      ui.emotionBadge.dataset.emotion = emotion;
    }
    if (window.YashiAvatar) YashiAvatar.setEmotion(emotion);
  }

  function updateMode(mode) {
    if (ui.modeBadge) {
      ui.modeBadge.textContent = mode;
      ui.modeBadge.dataset.mode = mode;
    }
  }

  function showTyping(show) {
    if (ui.typingIndicator) {
      ui.typingIndicator.style.display = show ? 'flex' : 'none';
    }
  }

  function setStatus(state, text) {
    if (ui.statusDot) ui.statusDot.dataset.state = state;
    if (ui.statusText) ui.statusText.textContent = text;
  }

  function clearChat() {
    if (ui.chatLog) ui.chatLog.innerHTML = '';
  }

  function scrollToBottom() {
    if (ui.chatLog) {
      ui.chatLog.scrollTop = ui.chatLog.scrollHeight;
    }
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', () => YashiClient.init());
