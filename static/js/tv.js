const tv = (selector) => document.querySelector(selector);
const soundEnabledKey = 'chama_clinica_sound_enabled';
const lastEventKey = 'chama_clinica_last_event';
let audioContext = null;
let currentEvent = null;
let ringTimer = null;

const formatTime = (value) => value ? new Date(value).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit', second: '2-digit'}) : '—';
const formatHour = (value) => value ? new Date(value).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'}) : '';

function setMessage(text, error = false) {
  tv('#tv-message [data-text]').textContent = text;
  tv('#tv-message').classList.toggle('text-rose-300', error);
  tv('#tv-conn').classList.toggle('off', error);
}

function setSoundButton(on) {
  tv('#sound-button [data-ico]').innerHTML = icon(on ? 'volume-2' : 'volume-x', 'h-4 w-4');
  tv('#sound-button [data-label]').textContent = on ? 'Som ativado' : 'Ativar som';
}

function tickClock() {
  const now = new Date();
  tv('#tv-clock').textContent = now.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
  tv('#tv-date').textContent = now.toLocaleDateString('pt-BR', {weekday: 'long', day: '2-digit', month: 'long'});
}

function beep() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    audioContext = audioContext || new AudioContext();
    const play = () => [880, 1175, 880].forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const at = audioContext.currentTime + index * 0.22;
      oscillator.type = 'sine'; oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.18, at + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.18);
      oscillator.connect(gain); gain.connect(audioContext.destination);
      oscillator.start(at); oscillator.stop(at + 0.2);
    });
    if (audioContext.state === 'suspended') audioContext.resume().then(play); else play();
  } catch (error) { setMessage('O navegador bloqueou o som. Clique em Ativar som.', true); }
}

function speak(current) {
  if (!('speechSynthesis' in window)) return;
  const message = `Paciente ${current.patient_name}. Dirija-se ao ${current.room}`;
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = 'pt-BR'; utterance.rate = 0.92;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function announce(current) {
  if (!current || localStorage.getItem(soundEnabledKey) !== '1') return;
  beep();
  setTimeout(() => speak(current), 750);
  localStorage.setItem(lastEventKey, current.event_token);
}

/* Anima o sino por alguns segundos a cada nova chamada ou rechamada */
function ring() {
  const bell = tv('#tv-bell');
  bell.classList.add('ringing');
  clearTimeout(ringTimer);
  ringTimer = setTimeout(() => bell.classList.remove('ringing'), 12000);
}

function render(data) {
  const current = data.current;
  const card = tv('#call-card');
  const bell = tv('#tv-bell');
  tv('#tv-queue').textContent = data.waiting_count;
  tv('#tv-status').textContent = data.status;
  tv('#tv-updated').textContent = formatTime(data.last_update);
  if (!current) {
    card.classList.add('waiting'); bell.classList.add('idle'); bell.classList.remove('ringing');
    tv('#tv-label').textContent = 'Aguardando chamada';
    tv('#tv-name').innerHTML = 'Nenhum paciente<br class="sm:hidden"> no momento';
    tv('#tv-room').classList.add('hidden'); tv('#tv-registration').classList.add('hidden');
    tv('#tv-called').textContent = '';
    currentEvent = null;
    return;
  }
  card.classList.remove('waiting'); bell.classList.remove('idle');
  tv('#tv-label').textContent = 'Chamando agora';
  tv('#tv-name').textContent = current.patient_name;
  tv('#tv-room [data-text]').textContent = current.room; tv('#tv-room').classList.remove('hidden');
  tv('#tv-registration').textContent = `Matrícula ${current.registration}`; tv('#tv-registration').classList.remove('hidden');
  tv('#tv-called').textContent = `Chamado às ${formatHour(current.called_at)}`;
  if (current.event_token !== currentEvent) {
    const name = tv('#tv-name');
    name.classList.remove('name-enter'); void name.offsetWidth; name.classList.add('name-enter');
    ring();
    if (current.event_token !== localStorage.getItem(lastEventKey)) announce(current);
  }
  currentEvent = current.event_token;
}

async function refresh() {
  try {
    const response = await fetch('/api/tv/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('TV não autorizada ou conexão indisponível.');
    render(await response.json());
    setMessage('Atualização automática a cada 2 segundos');
  } catch (error) { setMessage(error.message, true); }
}

tv('#sound-button').addEventListener('click', async () => {
  localStorage.setItem(soundEnabledKey, '1');
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) { audioContext = audioContext || new AudioContext(); await audioContext.resume(); }
    beep();
    setSoundButton(true);
    setMessage('Som ativado para novas chamadas e rechamadas.');
  } catch (error) { setMessage('Não foi possível ativar o som neste navegador.', true); }
});
tv('#fullscreen-button').addEventListener('click', () => {
  if (document.fullscreenElement) document.exitFullscreen?.(); else document.documentElement.requestFullscreen?.();
});
setSoundButton(localStorage.getItem(soundEnabledKey) === '1');
tickClock(); setInterval(tickClock, 1000);
refresh();
setInterval(refresh, 2000);
