const chat = document.getElementById('chat');
const projectSelect = document.getElementById('project');
const message = document.getElementById('message');
const send = document.getElementById('send');
const newThread = document.getElementById('new-thread');
const keyInput = document.getElementById('api-key');
const keyBar = document.getElementById('key-bar');
const threadLabel = document.getElementById('thread-label');

const KEY_STORAGE = 'griot.apiKey';
const THREAD_STORAGE = 'griot.threadId';

let threadId = null;

/** localStorage throws in private windows and with site data blocked. */
function readStored(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* non-fatal: the session still works, it just will not be remembered */
  }
}

function apiKey() {
  return (keyInput.value || '').trim();
}

function setThread(id) {
  threadId = id;
  writeStored(THREAD_STORAGE, id);
  threadLabel.textContent = id ? `thread ${id.slice(0, 8)}` : 'new thread';
}

function addBubble(text, role, meta = '') {
  const wrap = document.createElement('div');
  wrap.className = `bubble ${role}`;
  if (meta) {
    const m = document.createElement('div');
    m.className = 'meta';
    m.textContent = meta;
    wrap.appendChild(m);
  }
  const body = document.createElement('div');
  body.textContent = text;
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

function selectedLabel() {
  return projectSelect.options[projectSelect.selectedIndex].text;
}

async function ask() {
  const text = message.value.trim();
  if (!text) return;

  if (!apiKey()) {
    addBubble('Add your GRIOT API key above before sending a request.', 'agent', 'GRIOT');
    keyInput.focus();
    return;
  }

  addBubble(text, 'user', selectedLabel());
  message.value = '';
  send.disabled = true;
  send.textContent = 'Thinking…';

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey(),
      },
      body: JSON.stringify({
        message: text,
        project: projectSelect.value,
        thread_id: threadId,
        mode: 'think',
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (res.status === 401) {
      addBubble('That API key was rejected. Check it and try again.', 'agent', 'GRIOT · auth');
      return;
    }
    if (!res.ok) {
      throw new Error(data.detail || `Request failed (${res.status})`);
    }

    setThread(data.thread_id);
    writeStored(KEY_STORAGE, apiKey());

    const parts = [];
    if (data.agents?.length) parts.push(data.agents.join(' · '));
    if (data.history_turns) parts.push(`${data.history_turns} prior turns`);
    if (data.memory_used) parts.push(`${data.memory_used} memories`);
    if (data.memory_written) parts.push(`learned: ${data.memory_written}`);

    addBubble(data.answer, 'agent', `GRIOT · ${parts.join(' · ')}`);
  } catch (err) {
    addBubble(`I couldn't complete that request. ${err.message}`, 'agent', 'GRIOT error');
  } finally {
    send.disabled = false;
    send.textContent = 'Ask GRIOT';
  }
}

send.addEventListener('click', ask);

message.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ask();
});

newThread.addEventListener('click', () => {
  setThread(null);
  chat.replaceChildren();
  addBubble('New thread. Previous context is cleared; stored memory still applies.', 'agent', 'GRIOT');
});

keyInput.addEventListener('change', () => {
  writeStored(KEY_STORAGE, apiKey() || null);
  keyBar.classList.toggle('has-key', Boolean(apiKey()));
});

document.querySelectorAll('[data-prompt]').forEach((btn) => {
  btn.addEventListener('click', () => {
    message.value = `${btn.dataset.prompt}\n\n`;
    message.focus();
  });
});

// --- Boot --------------------------------------------------------------------

keyInput.value = readStored(KEY_STORAGE) || '';
keyBar.classList.toggle('has-key', Boolean(apiKey()));
setThread(readStored(THREAD_STORAGE));

fetch('/health')
  .then((r) => r.json())
  .then((h) => {
    const status = document.getElementById('status-detail');
    if (!status) return;
    const bits = [h.memory, h.model_ready ? h.model : 'no model key'];
    status.textContent = bits.join(' · ');
  })
  .catch(() => {});

addBubble(
  'I’m ready. Pick a project and tell me what you are trying to achieve, decide, diagnose, build or improve.',
  'agent',
  'GRIOT',
);
