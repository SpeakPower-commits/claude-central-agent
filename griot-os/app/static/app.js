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
const PROJECT_STORAGE = 'griot.project';

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

const G_MARK = `
<svg class="g-avatar" viewBox="0 0 64 64" aria-hidden="true">
  <defs><linearGradient id="gav" x1=".12" y1=".02" x2=".88" y2=".98">
    <stop offset="0" stop-color="#F2D67B"/><stop offset=".5" stop-color="#E0BE55"/>
    <stop offset="1" stop-color="#BA9622"/></linearGradient></defs>
  <path d="M 56.23 32 A 24.23 24.23 0 1 1 51.35 17.42" fill="none"
        stroke="url(#gav)" stroke-width="5.55" stroke-linecap="round"/>
  <path class="g-smile" d="M 38.8 37.0 Q 44.4 43.6 50.4 36.4" fill="none"
        stroke="url(#gav)" stroke-width="5.6" stroke-linecap="round"/>
  <g class="g-specs" fill="none" stroke="#FAF7EF" stroke-width="2.75" stroke-linejoin="round">
    <rect x="18.83" y="22.18" width="11.80" height="8.55" rx="2.1"/>
    <rect x="35.05" y="22.18" width="13.79" height="8.55" rx="2.1"/>
  </g>
  <path d="M 31.9 26.3 H 34.0" stroke="#FAF7EF" stroke-width="1.9" stroke-linecap="round"/>
</svg>`;

function addBubble(text, role, meta = '') {
  const wrap = document.createElement('div');
  wrap.className = `bubble ${role}`;
  if (role === 'agent') wrap.insertAdjacentHTML('afterbegin', G_MARK);
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
  const opt = projectSelect.options[projectSelect.selectedIndex];
  return opt ? opt.text : 'Portfolio';
}


/** Populate the project dropdown from the API.
 *  /projects is authenticated, so this runs once a key is available and again
 *  whenever the key changes. Without a key we show a prompt rather than an
 *  empty box, so the UI explains itself.
 */
async function loadProjects() {
  const placeholder = (text) => {
    projectSelect.replaceChildren();
    const o = document.createElement('option');
    o.textContent = text;
    o.value = '';
    projectSelect.appendChild(o);
  };

  if (!apiKey()) {
    placeholder('Add your API key first');
    return;
  }

  try {
    const res = await fetch('/projects', { headers: { 'X-API-Key': apiKey() } });
    if (!res.ok) {
      placeholder(res.status === 401 ? 'Invalid API key' : 'Could not load projects');
      return;
    }
    const projects = await res.json();
    const previous = readStored(PROJECT_STORAGE);
    projectSelect.replaceChildren();
    for (const [slug, meta] of Object.entries(projects)) {
      const o = document.createElement('option');
      o.value = slug;
      o.textContent = meta.name || slug;
      o.title = meta.description || '';
      projectSelect.appendChild(o);
    }
    if (previous && projects[previous]) projectSelect.value = previous;
  } catch {
    placeholder('Could not load projects');
  }
}

async function ask() {
  const text = message.value.trim();
  if (!text) return;

  if (!apiKey()) {
    addBubble('Add your GRIOT API key above before sending a request.', 'agent', 'GRIOT');
    keyInput.focus();
    return;
  }

  if (!projectSelect.value) {
    addBubble('Pick a project first.', 'agent', 'GRIOT');
    return;
  }
  writeStored(PROJECT_STORAGE, projectSelect.value);
  addBubble(text, 'user', selectedLabel());
  message.value = '';
  send.disabled = true;
  send.textContent = 'Thinking…';
  document.body.dataset.griot = 'thinking';

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
    document.body.dataset.griot = 'idle';
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
  loadProjects();
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
loadProjects();

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
