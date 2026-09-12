const chat = document.getElementById('chat');
const project = document.getElementById('project');
const message = document.getElementById('message');
const send = document.getElementById('send');

function addBubble(text, role, meta = '') {
  const wrap = document.createElement('article');
  wrap.className = `bubble ${role}`;
  if (meta) {
    const m = document.createElement('div');
    m.className = 'meta';
    m.textContent = meta;
    wrap.appendChild(m);
  }
  const body = document.createElement('div');
  body.className = 'bubble-body';
  body.textContent = text;
  wrap.appendChild(body);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

function selectedLabel() {
  return project.options[project.selectedIndex].text;
}

async function ask() {
  const text = message.value.trim();
  if (!text) return;
  addBubble(text, 'user', selectedLabel());
  message.value = '';
  send.disabled = true;
  send.textContent = 'Thinking…';

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, project: project.value, mode: 'think' })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    const meta = data.agents?.length ? data.agents.join(' · ') : 'StrategyAgent';
    addBubble(data.answer, 'agent', `GRIOT · ${meta} · memory ${data.memory_used ?? 0}`);
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

document.querySelectorAll('[data-prompt]').forEach((button) => {
  button.addEventListener('click', () => {
    message.value = `${button.dataset.prompt}\n\n`;
    message.focus();
  });
});

addBubble(
  'I’m ready. Pick a project and tell me what you are trying to achieve, decide, diagnose, build or improve.',
  'agent',
  'GRIOT OS'
);
