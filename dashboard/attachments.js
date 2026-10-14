// Clipboard image drafts belong to a session, and are removed only after a successful send.
const TYPES = new Set(['image/png','image/jpeg','image/gif','image/webp']);
export class Attachments {
  constructor({session, error, changed}) {
    Object.assign(this, {session,error,changed});
    this.drafts = new Map(); this.loading = new Map();
    this.tray = document.querySelector('#attachments');
    document.querySelector('#draft').addEventListener('paste', e => this.paste(e));
  }
  items(sid = this.session()) { return this.drafts.get(sid) || []; }
  busy(sid = this.session()) { return Boolean(this.loading.get(sid)); }
  render() {
    this.tray.replaceChildren();
    this.tray.hidden = !this.items().length && !this.busy();
    for (const item of this.items()) {
      const card = document.createElement('div'); card.className = 'attachment';
      const img = document.createElement('img'); img.src = item.url; img.alt = item.name;
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
      remove.setAttribute('aria-label', 'Remove '+item.name);
      remove.onclick = () => { this.clear(this.session(), [item]); this.changed(); };
      card.append(img,remove); this.tray.append(card);
    }
    if (this.busy()) { const label = document.createElement('span'); label.textContent = 'Reading pasted image…'; this.tray.append(label); }
  }
  clear(sid, sent) {
    this.drafts.set(sid, this.items(sid).filter(i => !sent.includes(i)));
    this.render();
  }
  async paste(e) {
    const files = [...(e.clipboardData?.items || [])].filter(i => i.kind === 'file' && i.type.startsWith('image/')).map(i => i.getAsFile()).filter(Boolean);
    if (!files.length) return; // ordinary text pastes retain native behavior
    e.preventDefault();
    const sid = this.session();
    if (!sid || e.currentTarget.disabled) return;
    this.loading.set(sid, (this.loading.get(sid) || 0) + 1); this.changed();
    try {
      for (const file of files) {
        if (!TYPES.has(file.type)) throw new Error('Paste a PNG, JPEG, GIF or WebP image.');
        if (file.size > 4*1024*1024) throw new Error('Each image must be at most 4 MB.');
        if (this.items(sid).length >= 4) throw new Error('Send up to four images at a time.');
        const url = await new Promise((resolve,reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error('Could not read the pasted image.')); reader.readAsDataURL(file);
        });
        // Recheck after reading: another paste may have completed in the meantime.
        if (this.items(sid).length >= 4 || this.items(sid).reduce((n,i)=>n+i.size,0)+file.size > 12*1024*1024) throw new Error('Send up to four images, totalling at most 12 MB.');
        const item = {name:file.name || 'Pasted image', size:file.size, url, source:{type:'base64',media_type:file.type,data:url.split(',')[1]}};
        this.drafts.set(sid,[...this.items(sid),item]);
      }
    } catch(err) { this.error(err.message); }
    finally { this.loading.set(sid, this.loading.get(sid)-1); this.changed(); }
  }
}
