const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const formatTime = (value) => value ? new Date(value).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'}) : '—';
const formatShort = (value) => value ? new Date(value).toLocaleString('pt-BR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}) : '—';
const initials = (name) => String(name || '?').trim().split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || '?';

function waitLabel(createdAt) {
  if (!createdAt) return '';
  const minutes = Math.max(0, Math.round((Date.now() - new Date(createdAt).getTime()) / 60000));
  if (minutes < 1) return 'agora';
  if (minutes < 60) return `há ${minutes} min`;
  return `há ${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

const STATUS = {
  finalizado: {label: 'Finalizado', icon: 'circle-check'},
  cancelado: {label: 'Cancelado', icon: 'circle-x'},
  chamado: {label: 'Em atendimento', icon: 'phone-call'},
  aguardando: {label: 'Aguardando', icon: 'hourglass'},
};

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { window.location.href = '/login'; throw new Error('Sessão expirada.'); }
  if (!response.ok) throw new Error(data.error || `Erro HTTP ${response.status}`);
  return data;
}

/* ---------- Toasts ---------- */
function toast(text, type = 'success') {
  if (!text) return;
  const box = document.createElement('div');
  box.className = `toast toast-${type}`;
  box.innerHTML = `<span class="toast-ico">${icon(type === 'error' ? 'circle-x' : 'circle-check', 'h-5 w-5 shrink-0')}</span><span>${escapeHtml(text)}</span>`;
  $('#toasts').appendChild(box);
  setTimeout(() => { box.style.transition = 'opacity .25s, transform .25s'; box.style.opacity = '0'; box.style.transform = 'translateY(8px)'; setTimeout(() => box.remove(), 260); }, 3600);
}

/* ---------- Conexão ---------- */
function setLive(ok, text) {
  $('#live-dot').classList.toggle('off', !ok);
  $('#dashboard-updated').textContent = text;
  const pill = $('#live-pill');
  pill.classList.toggle('bg-emerald-50', ok); pill.classList.toggle('text-emerald-700', ok); pill.classList.toggle('ring-emerald-100', ok);
  pill.classList.toggle('bg-rose-50', !ok); pill.classList.toggle('text-rose-700', !ok); pill.classList.toggle('ring-rose-100', !ok);
}

/* ---------- Render ---------- */
let busy = false;
let lastQueueSig = '';
let lastCurrentSig = '';

function renderCurrent(current) {
  const sig = JSON.stringify(current);
  $('#current-empty').hidden = Boolean(current);
  $('#current-content').hidden = !current;
  if (!current || sig === lastCurrentSig) { lastCurrentSig = sig; return; }
  lastCurrentSig = sig;
  $('#current-name').textContent = current.patient_name;
  $('#current-registration').textContent = current.registration;
  $('#current-room').textContent = current.room;
  $('#current-called').textContent = formatTime(current.called_at);
  $('#finish-button').dataset.id = current.id;
  $('#recall-button').dataset.id = current.id;
}

function renderQueue(items) {
  $('#waiting-count').textContent = items.length;
  $('#hero-count').textContent = items.length;
  $('#next-button').disabled = busy || items.length === 0;
  const sig = items.map((item) => `${item.id}:${item.patient_name}:${item.room}`).join('|');
  const list = $('#queue-list');
  if (sig === lastQueueSig) {
    // atualiza apenas o tempo de espera, sem recriar a lista
    list.querySelectorAll('[data-created]').forEach((node) => { node.textContent = waitLabel(node.dataset.created); });
    return;
  }
  lastQueueSig = sig;
  if (!items.length) {
    list.innerHTML = `<div class="flex flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 py-10 text-center"><span class="mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-white text-ink-400 shadow-card">${icon('inbox', 'h-6 w-6')}</span><p class="font-display font-extrabold">A fila está vazia</p><p class="mt-1 text-sm text-ink-500">Novos pacientes aparecem aqui automaticamente.</p></div>`;
    return;
  }
  list.innerHTML = items.map((item, index) => `
    <div class="queue-item" style="animation-delay:${Math.min(index, 8) * 40}ms">
      <div class="avatar">${escapeHtml(initials(item.patient_name))}</div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2"><span class="pos">${index + 1}º</span><strong class="truncate font-display text-[15px] font-bold">${escapeHtml(item.patient_name)}</strong></div>
        <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs font-medium text-ink-500">
          <span>Mat. ${escapeHtml(item.registration)}</span>
          <span class="inline-flex items-center gap-1">${icon('door-open', 'h-3.5 w-3.5')}${escapeHtml(item.room)}</span>
          <span class="inline-flex items-center gap-1">${icon('clock', 'h-3.5 w-3.5')}<span data-created="${escapeHtml(item.created_at)}">${waitLabel(item.created_at)}</span></span>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-1.5">
        <button class="btn-soft btn-sm call-specific" data-id="${item.id}" type="button">${icon('phone-call', 'h-4 w-4')}<span class="hidden sm:inline">Chamar</span></button>
        <button class="btn-ghost btn-sm cancel-specific !px-2" data-id="${item.id}" type="button" aria-label="Cancelar paciente">${icon('x', 'h-4 w-4')}</button>
      </div>
    </div>`).join('');
}

/* Delegação de eventos: a lista é recriada, então ouvimos no container */
$('#queue-list').addEventListener('click', (event) => {
  const call = event.target.closest('.call-specific');
  const cancel = event.target.closest('.cancel-specific');
  if (call) mutate(`/api/calls/${call.dataset.id}/call`, 'Paciente chamado.');
  if (cancel) {
    if (cancel.dataset.armed === '1') { mutate(`/api/calls/${cancel.dataset.id}/cancel`, 'Paciente cancelado.'); return; }
    cancel.dataset.armed = '1';
    cancel.className = 'btn-danger btn-sm cancel-specific';
    cancel.innerHTML = 'Confirmar?';
    setTimeout(() => { if (cancel.isConnected) { cancel.dataset.armed = ''; cancel.className = 'btn-ghost btn-sm cancel-specific !px-2'; cancel.innerHTML = icon('x', 'h-4 w-4'); } }, 3000);
  }
});

async function refreshDashboard() {
  try {
    const data = await api('/api/dashboard');
    renderCurrent(data.current);
    renderQueue(data.waiting);
    setLive(true, `Ao vivo · ${new Date().toLocaleTimeString('pt-BR')}`);
  } catch (error) { setLive(false, 'Sem conexão'); }
}

async function refreshHistory() {
  try {
    const data = await api('/api/history?limit=30');
    $('#history-list').innerHTML = data.items.length ? data.items.map((item) => {
      const status = STATUS[item.status] || {label: item.status, icon: 'activity'};
      return `<div class="flex items-center gap-3 py-3">
        <div class="avatar !h-10 !w-10 !rounded-lg !text-xs">${escapeHtml(initials(item.patient_name))}</div>
        <div class="min-w-0 flex-1"><div class="truncate font-display text-sm font-bold">${escapeHtml(item.patient_name)}</div><div class="truncate text-xs font-medium text-ink-500">Mat. ${escapeHtml(item.registration)} · ${escapeHtml(item.room)}</div></div>
        <div class="shrink-0 text-right"><span class="badge badge-${escapeHtml(item.status)}">${icon(status.icon, 'h-3 w-3')}${status.label}</span><div class="mt-1 text-[11px] font-medium text-ink-400">${formatShort(item.updated_at)}</div></div>
      </div>`;
    }).join('') : `<p class="py-8 text-center text-sm text-ink-500">Ainda não há histórico.</p>`;
  } catch (error) { toast(error.message, 'error'); }
}

async function mutate(url, successMessage) {
  if (busy) return;
  busy = true;
  document.querySelectorAll('#next-button, #finish-button, #recall-button, .call-specific').forEach((button) => { button.disabled = true; });
  try { await api(url, {method: 'POST'}); toast(successMessage, 'success'); }
  catch (error) { toast(error.message, 'error'); }
  finally { busy = false; await refreshDashboard(); await refreshHistory(); document.querySelectorAll('#finish-button, #recall-button, .call-specific').forEach((button) => { button.disabled = false; }); }
}

$('#add-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $('#add-button');
  const data = Object.fromEntries(new FormData(form).entries());
  button.disabled = true;
  try {
    await api('/api/patients', {method: 'POST', body: JSON.stringify(data)});
    form.reset(); form.room.value = data.room || 'Consultório 1';
    form.patient_name.focus();
    toast('Paciente adicionado à fila.', 'success');
    await refreshDashboard();
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
});
$('#next-button').addEventListener('click', () => mutate('/api/calls/next', 'Próximo paciente chamado.'));
$('#finish-button').addEventListener('click', (event) => mutate(`/api/calls/${event.currentTarget.dataset.id}/finish`, 'Atendimento finalizado.'));
$('#recall-button').addEventListener('click', (event) => mutate(`/api/calls/${event.currentTarget.dataset.id}/recall`, 'Paciente rechamado.'));
$('#refresh-history').addEventListener('click', refreshHistory);
refreshDashboard();
refreshHistory();
setInterval(refreshDashboard, 2000);
