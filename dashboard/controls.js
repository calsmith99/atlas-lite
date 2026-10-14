// Session-scoped controls. No provider selection or personal home integrations.
const $ = (s) => document.querySelector(s);
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export async function post(url, data) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || `Request failed (${r.status})`);
  return body;
}
export class WorkControls {
  constructor({session, meta, error, markdown}) {
    Object.assign(this, {session, meta, error, markdown});
    this.status = {}; this.permissions = new Map(); this.usage = {}; this.windows = {};
    this.connected = false; this.listening = false; this.voice = false;
    $('#close-preview').onclick = () => this.closePreview();
    $('#open-file').onclick = () => this.fileForm();
    $('#stop').onclick = async () => {
      const sid = this.session();
      if (!sid) return;
      try { await post(`/api/session/${sid}/interrupt`, {}); } catch(e) { this.error(e.message); }
    };
    document.addEventListener('keydown', e => { if (e.key === 'Escape') this.closePreview(); });
  }
  restore(runtime = {}) {
    this.status = runtime.status || {};
    this.permissions = new Map((runtime.permissions || []).map(p => [p.id, p]));
    this.usage = runtime.usage || {}; this.windows = runtime.usageWindows || {};
    this.render();
  }
  event(m) {
    if (m.t === 'status') this.status[m.session] = {stage:m.stage, text:m.text};
    if (m.t === 'permission') this.permissions.set(m.id, m);
    if (m.t === 'permission_done') this.permissions.delete(m.id);
    if (m.t === 'usage') { this.usage[m.session] = m.usage; this.windows = m.windows || this.windows; }
    this.render(m.t === 'permission' || m.t === 'permission_done');
  }
  connection(on) { this.connected = on; this.render(); }
  render(decisions = true) {
    const sid = this.session(), meta = this.meta(), s = this.status[sid];
    $('#connection').textContent = this.connected ? 'Connected' : 'Disconnected · Reconnecting…';
    $('#connection').classList.toggle('error', !this.connected);
    $('#input-state').textContent = this.listening ? 'Listening · Send when ready' : this.voice ? 'Typed input · Voice ready' : 'Typed input · Voice off';
    const waiting = [...this.permissions.values()].some(p => p.session === sid);
    $('#task-state').textContent = !sid ? 'Choose a conversation' : waiting ? 'Waiting for your answer' : s?.text || (meta?.working ? 'Working on your message' : 'Ready for your next message');
    $('#stop').hidden = !meta?.driving;
    $('#stop').disabled = !this.connected;
    $('#send').textContent = meta?.driving ? 'Send correction' : 'Send';
    $('#open-file').disabled = !sid || !this.connected;
    this.renderUsage();
    if (decisions) this.renderDecision();
  }
  renderUsage() {
    const u = this.usage[this.session()], rows = [];
    for (const [key, title] of [['five_hour','Five hours'], ['seven_day','Weekly'], ...[['seven_day_opus','Weekly Opus'], ['seven_day_sonnet','Weekly Sonnet'], ['overage','Extra usage']].filter(([key]) => this.windows[key])]) {
      const w = this.windows[key], n = Number(w?.utilization);
      const reset = Number(w?.resetsAt);
      const label = w && Number.isFinite(n) ? `${Math.round(n * 100)}% used` : 'Not reported yet';
      rows.push(`<div class="usage-row"><span>${title}</span><span>${label}</span></div>${w && Number.isFinite(n) ? `<progress max="1" value="${Math.max(0,Math.min(1,n))}" aria-label="${title} usage"></progress>` : ''}${reset ? `<small>Resets ${esc(new Date(reset * 1000).toLocaleString())}</small>` : ''}`);
    }
    if (u?.at) {
      const fmt = n => Number(n || 0).toLocaleString();
      rows.push(`<div class="usage-detail">Last turn: ${fmt(u.input)} input · ${fmt(u.output)} output tokens<br>${fmt(u.cached)} cached · ${fmt(u.cacheCreated)} cache created${u.cost != null ? `<br>Reported session cost $${Number(u.cost).toFixed(4)}` : ''}</div>`);
    } else rows.push('<p class="muted">Figures appear when Claude reports them.</p>');
    $('#usage').innerHTML = rows.join('');
  }
  frame() { $('#preview').hidden = $('#artifact').hidden && $('#decision').hidden; }
  closePreview() { $('#artifact').hidden = true; $('#artifact-body').replaceChildren(); this.frame(); }
  artifact(title) {
    $('#artifact-title').textContent = title; $('#artifact').hidden = false;
    $('#artifact-body').replaceChildren(); this.frame(); return $('#artifact-body');
  }
  async copy(text, button) {
    try { await navigator.clipboard.writeText(text); button.textContent = 'Copied'; }
    catch { button.textContent = 'Select and copy'; const pre = button.parentElement.querySelector('pre'); if (pre) { const range = document.createRange(); range.selectNodeContents(pre); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range); } }
  }
  commands(blocks) {
    const body = this.artifact('Copy code');
    for (const {label,text} of blocks) {
      const row = document.createElement('div'); row.className = 'command-block';
      row.innerHTML = `<span>${esc(label || 'Code')}</span><button type="button">Copy</button><pre></pre>`;
      row.querySelector('pre').textContent = text;
      row.querySelector('button').onclick = e => this.copy(text, e.currentTarget);
      body.append(row);
    }
  }
  decorate(body, live = false) {
    const blocks = [...body.querySelectorAll('pre code')].map(el => ({label:el.className.replace('language-','') || 'Code', text:el.textContent}));
    if (blocks.length) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'copy-blocks'; button.textContent = 'Copy code…';
      button.onclick = () => this.commands(blocks); body.append(button);
      if (live) this.commands(blocks);
    }
    for (const a of body.querySelectorAll('a')) {
      const href = a.getAttribute('href') || '';
      if (href.startsWith('/') && !href.startsWith('//') || href.startsWith('file://')) {
        a.onclick = e => { e.preventDefault(); try { this.preview(decodeURIComponent(href.replace(/^file:\/\//,'')).replace(/:\d+(?::\d+)?$/, '')); } catch { this.error('Invalid file link'); } };
      } else { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    }
  }
  fileForm() {
    const body = this.artifact('Preview a file');
    body.innerHTML = '<form class="file-form"><label>File path<input name="path" placeholder="Path relative to this project, or absolute" required></label><button>Open</button></form>';
    const form = body.querySelector('form'); form.onsubmit = e => { e.preventDefault(); this.preview(form.elements.path.value); };
    form.elements.path.focus();
  }
  async preview(path) {
    const sid = this.session(); if (!sid) return;
    try {
      const url = `/api/session/${sid}/preview?path=${encodeURIComponent(path)}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(await r.text());
      const file = await r.json();
      if (sid !== this.session()) return;
      const body = this.artifact(file.name);
      if (file.kind === 'image') { const img = document.createElement('img'); img.alt = file.name; img.src = url + '&raw=1'; body.append(img); }
      else if (file.kind === 'pdf') { const frame = document.createElement('iframe'); frame.title = file.name; frame.src = url + '&raw=1'; body.append(frame); }
      else if (file.kind === 'markdown') { body.innerHTML = this.markdown(file.text); this.decorate(body); }
      else { const pre = document.createElement('pre'); pre.textContent = file.text; body.append(pre); }
    } catch(e) { this.error(e.message); }
  }
  renderDecision() {
    const p = [...this.permissions.values()].find(p => p.session === this.session());
    const card = $('#decision');
    // Preserve in-progress typing while unrelated events stream in.
    if (p && card.dataset.request === p.id) { card.hidden = false; this.frame(); return; }
    card.dataset.request = p?.id || ''; card.replaceChildren(); card.hidden = !p;
    this.frame(); if (!p) return;
    const isQuestion = p.tool === 'AskUserQuestion';
    const title = document.createElement('h2'); title.textContent = isQuestion ? 'Your answer' : `Allow ${p.tool}?`; card.append(title);
    const form = document.createElement('form'); card.append(form);
    if (isQuestion) {
      for (const [i,q] of (p.input.questions || []).entries()) {
        const field = document.createElement('fieldset');
        const legend = document.createElement('legend'); legend.textContent = q.question; field.append(legend);
        for (const o of q.options || []) {
          const label = document.createElement('label'); label.className = 'choice';
          const input = document.createElement('input'); input.type = q.multiSelect ? 'checkbox' : 'radio'; input.name = 'q'+i; input.value = o.label;
          label.append(input, document.createTextNode(o.label + (o.description ? ' — '+o.description : ''))); field.append(label);
        }
        const label = document.createElement('label'); label.className = 'choice'; label.textContent = 'Something else';
        const input = document.createElement('textarea'); input.name = 'other'+i; input.rows = 2; label.append(input); field.append(label); form.append(field);
      }
    } else {
      const desc = document.createElement('p'); desc.textContent = p.description; form.append(desc);
      const pre = document.createElement('pre'); pre.textContent = JSON.stringify(p.input, null, 2); form.append(pre);
    }
    const error = document.createElement('p'); error.className = 'error'; error.setAttribute('role','alert'); form.append(error);
    const buttons = document.createElement('div'); buttons.className = 'decision-buttons'; form.append(buttons);
    const yes = document.createElement('button'); yes.textContent = isQuestion ? 'Continue' : 'Allow once'; yes.type = 'submit'; buttons.append(yes);
    const no = document.createElement('button'); no.textContent = isQuestion ? 'Decline' : 'Deny'; no.type = 'button'; buttons.append(no);
    const submit = async allow => {
      const answers = {};
      if (allow && isQuestion) for (const [i,q] of (p.input.questions || []).entries()) {
        const other = form.elements['other'+i].value.trim();
        const selected = [...form.querySelectorAll(`input[name="q${i}"]:checked`)].map(el => el.value);
        const value = other || selected.join(', ');
        if (!value) { error.textContent = 'Answer each question or choose Decline.'; return; }
        answers[q.question] = value;
      }
      yes.disabled = no.disabled = true;
      try {
        await post(`/api/session/${p.session}/permission/${encodeURIComponent(p.id)}`, {allow, answers});
        this.permissions.delete(p.id); this.renderDecision();
      } catch(e) { error.textContent = e.message; yes.disabled = no.disabled = false; }
    };
    form.onsubmit = e => { e.preventDefault(); submit(true); }; no.onclick = () => submit(false);
  }
}
