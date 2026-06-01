// Dashboard "Mis módulos": habla con el runtime Rust real (vía proxy /api del mismo origen).
const ICONS = { inventory: '📦', notes: '🗒️' };
const grid = document.getElementById('grid');

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

async function load() {
  const { data: mods } = await api('/api/modules');
  if (!mods || mods.length === 0) { grid.innerHTML = '<div class="empty">No hay módulos instalados.</div>'; return; }
  grid.innerHTML = '';
  for (const m of mods) {
    const active = m.status === 'active';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="top">
        <div class="ico">${ICONS[m.id] || '🧩'}</div>
        <div><div class="name">${m.name}</div><div class="ver">v${m.version} · ${m.id}</div></div>
        <span class="badge ${active ? 'active' : 'inactive'}">${active ? 'Activo' : 'Inactivo'}</span>
      </div>
      <div class="row">
        ${active
          ? `<button class="warn" data-act="deactivate" data-id="${m.id}">Desactivar</button>`
          : `<button class="primary" data-act="activate" data-id="${m.id}">Activar</button>`}
        <button data-act="uninstall" data-id="${m.id}">Desinstalar</button>
      </div>`;
    grid.appendChild(card);
  }
  grid.querySelectorAll('button[data-act]').forEach((b) =>
    b.addEventListener('click', async () => {
      await api(`/api/modules/${b.dataset.id}/${b.dataset.act}`, { method: 'POST' });
      load();
    }),
  );
}
load();
