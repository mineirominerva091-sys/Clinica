import sqlite3
import os
import json
import time
import html
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

APP_TITLE = "Chama Clínica"
DB_PATH = os.environ.get("CLINICA_DB_PATH", "clinica.db")

st.set_page_config(page_title=APP_TITLE, page_icon="🔔", layout="wide", initial_sidebar_state="collapsed")

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            registration TEXT NOT NULL,
            room TEXT DEFAULT 'Consultório',
            status TEXT NOT NULL DEFAULT 'aguardando',
            created_at TEXT NOT NULL,
            called_at TEXT
        )
    """)
    conn.commit()
    return conn

def get_current():
    conn = db()
    row = conn.execute("SELECT * FROM calls WHERE status='chamado' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None

def get_waiting():
    conn = db()
    rows = conn.execute("SELECT * FROM calls WHERE status='aguardando' ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent(limit=12):
    conn = db()
    rows = conn.execute("SELECT * FROM calls WHERE status IN ('chamado','finalizado','cancelado') ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_patient(name, registration, room):
    conn = db()
    conn.execute("INSERT INTO calls(patient_name, registration, room, status, created_at) VALUES(?,?,?,?,?)",
                 (name.strip(), registration.strip(), room.strip() or "Consultório", "aguardando", datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    conn.commit()
    conn.close()

def call_next():
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT id FROM calls WHERE status='aguardando' ORDER BY id ASC LIMIT 1").fetchone()
    if row:
        conn.execute("UPDATE calls SET status='finalizado' WHERE status='chamado'")
        conn.execute("UPDATE calls SET status='chamado', called_at=? WHERE id=?",
                     (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), row["id"]))
    conn.commit()
    conn.close()
    return bool(row)

def call_specific(call_id):
    conn = db()
    conn.execute("UPDATE calls SET status='finalizado' WHERE status='chamado'")
    conn.execute("UPDATE calls SET status='chamado', called_at=? WHERE id=? AND status='aguardando'",
                 (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), int(call_id)))
    conn.commit()
    changed = conn.execute("SELECT changes()").fetchone()[0]
    conn.close()
    return changed > 0

def mark_done(call_id):
    conn = db()
    conn.execute("UPDATE calls SET status='finalizado' WHERE id=? AND status='chamado'", (int(call_id),))
    conn.commit()
    conn.close()

def cancel_waiting(call_id):
    conn = db()
    conn.execute("UPDATE calls SET status='cancelado' WHERE id=? AND status='aguardando'", (int(call_id),))
    conn.commit()
    conn.close()

def reset_demo():
    conn = db()
    conn.execute("DELETE FROM calls")
    conn.commit()
    conn.close()

def sound_widget(call_id, patient_name, registration, room):
    # The browser may block autoplay until the user interacts with the page. The screen includes an enable-sound button.
    safe_name = json.dumps(patient_name)
    safe_reg = json.dumps(registration)
    safe_room = json.dumps(room)
    components.html(f"""
    <div id="sound-area" style="font-family:Arial,sans-serif;color:#64748b;font-size:12px">Notificação sonora ativa quando permitida pelo navegador.</div>
    <script>
    const callId = {int(call_id)};
    const name = {safe_name};
    const reg = {safe_reg};
    const room = {safe_room};
    const key = 'chama_clinica_last_sound_id';
    let last = Number(localStorage.getItem(key) || '0');
    function beep() {{
      try {{
        const Ctx = window.AudioContext || window.webkitAudioContext;
        const ctx = new Ctx();
        if (ctx.state === 'suspended') ctx.resume();
        const notes = [880, 1175, 880];
        notes.forEach((freq, i) => {{
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine'; osc.frequency.value = freq;
          gain.gain.setValueAtTime(0.0001, ctx.currentTime + i*0.22);
          gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + i*0.22 + 0.03);
          gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i*0.22 + 0.18);
          osc.connect(gain); gain.connect(ctx.destination);
          osc.start(ctx.currentTime + i*0.22); osc.stop(ctx.currentTime + i*0.22 + 0.2);
        }});
        if ('speechSynthesis' in window) {{
          setTimeout(() => {{
            const u = new SpeechSynthesisUtterance('Paciente ' + name + '. Matrícula ' + reg + '. Dirija-se ao ' + room);
            u.lang = 'pt-BR'; u.rate = 0.92; window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
          }}, 750);
        }}
      }} catch(e) {{}}
    }}
    if (callId > 0 && callId > last) {{
      localStorage.setItem(key, String(callId));
      beep();
    }}
    </script>
    """, height=28)

def status_label(status):
    return {"aguardando":"Aguardando", "chamado":"Chamado", "finalizado":"Finalizado", "cancelado":"Cancelado"}.get(status, status)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {font-family:'DM Sans',sans-serif;}
.stApp {background:linear-gradient(135deg,#f4f7fb 0%,#eef3f9 100%);}
.block-container {padding-top:1.5rem;max-width:1250px;}
.hero {background:linear-gradient(120deg,#10243a,#1d4668);padding:26px 30px;border-radius:22px;color:white;margin-bottom:22px;box-shadow:0 12px 28px rgba(16,36,58,.13);}
.hero h1 {font-size:30px;line-height:1.15;margin:0 0 8px 0;font-weight:800;}
.hero p {margin:0;color:#d5e4f3;font-size:14px;}
.panel {background:white;border:1px solid #e1e8f0;border-radius:18px;padding:22px;box-shadow:0 6px 18px rgba(28,50,77,.045);margin-bottom:16px;}
.muted {color:#64748b;font-size:13px;}
.big-name {font-size:clamp(28px,4vw,46px);font-weight:800;line-height:1.1;color:#12263a;overflow-wrap:anywhere;}
.big-reg {font-size:18px;color:#52667c;margin-top:10px;}
.kicker {font-size:11px;font-weight:800;letter-spacing:1.5px;color:#64819c;text-transform:uppercase;}
.wait-number {font-size:26px;font-weight:800;color:#153550;}
div.stButton > button {border-radius:12px;font-weight:700;min-height:44px;}
div[data-testid="stForm"] {border:0;padding:0;}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hero">
  <h1>🔔 {APP_TITLE}</h1>
  <p>Sistema simples de chamada de pacientes • ambiente de demonstração</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("Navegação")
    view = st.radio("Escolha a tela", ["Painel da médica", "Tela da recepção / TV", "Histórico e configurações"])
    st.divider()
    st.caption("Protótipo de teste. Evite inserir dados pessoais reais.")

if view == "Painel da médica":
    current = get_current()
    waiting = get_waiting()
    col1, col2 = st.columns([1.05, 1.2], gap="large")
    with col1:
        st.markdown('<div class="panel"><div class="kicker">Atendimento atual</div>', unsafe_allow_html=True)
        if current:
            st.markdown(f'<div class="big-name">{html.escape(current["patient_name"])}</div><div class="big-reg">Matrícula: <b>{html.escape(current["registration"])}</b></div><p class="muted">Local: {html.escape(current["room"])} • Chamado às {html.escape(current["called_at"] or "—")}</p>', unsafe_allow_html=True)
            a, b = st.columns(2)
            with a:
                if st.button("✓ Finalizar atendimento", use_container_width=True):
                    mark_done(current["id"]); st.rerun()
            with b:
                if st.button("🔔 Rechamar paciente", use_container_width=True):
                    # Update timestamp to force notification in a refreshed display.
                    conn = db()
                    conn.execute("UPDATE calls SET called_at=? WHERE id=?", (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), current["id"]))
                    conn.commit(); conn.close()
                    st.success("Paciente marcado para rechamada. Atualize a tela da TV para repetir o aviso.")
        else:
            st.markdown('<div class="big-name">Nenhum paciente chamado</div><p class="muted">Use “Chamar próximo” ou selecione alguém da fila.</p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        if st.button("▶️ Chamar próximo da fila", type="primary", use_container_width=True, disabled=(len(waiting)==0)):
            if call_next():
                st.success("Próximo paciente chamado!")
                st.rerun()
        st.caption(f"Pacientes aguardando: **{len(waiting)}**")
    with col2:
        st.markdown('<div class="panel"><div class="kicker">Adicionar paciente à fila</div>', unsafe_allow_html=True)
        with st.form("add_patient_form", clear_on_submit=True):
            name = st.text_input("Nome do paciente", placeholder="Ex.: Maria da Silva", max_chars=100)
            registration = st.text_input("Matrícula / identificação", placeholder="Ex.: 123456", max_chars=40)
            room = st.text_input("Consultório / destino", value="Consultório 1", max_chars=60)
            submitted = st.form_submit_button("＋ Adicionar à fila", use_container_width=True)
            if submitted:
                if not name.strip() or not registration.strip():
                    st.error("Preencha o nome e a matrícula.")
                else:
                    add_patient(name, registration, room)
                    st.success(f"{name.strip()} adicionado(a) à fila.")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel"><div class="kicker">Fila de espera</div>', unsafe_allow_html=True)
        if waiting:
            for i, p in enumerate(waiting, start=1):
                with st.container(border=True):
                    x, y = st.columns([3,1])
                    with x:
                        st.markdown(f'**{i}. {html.escape(p["patient_name"])}**')
                        st.caption(f'Matrícula: {html.escape(p["registration"])} · {html.escape(p["room"])}')
                    with y:
                        if st.button("Chamar", key=f'call_{p["id"]}', use_container_width=True):
                            call_specific(p["id"]); st.rerun()
        else:
            st.info("A fila está vazia. Adicione um paciente para começar.")
        st.markdown('</div>', unsafe_allow_html=True)


elif view == "Tela da recepção / TV":

    @st.fragment(run_every="2s")
    def renderizar_painel_tv():
        # Consultar novamente os dados a cada atualização
        current = get_current()
        waiting = get_waiting()

        st.markdown(
            '<div class="panel" style="text-align:center;padding:36px 24px">'
            '<div class="kicker">Atenção • Próximo atendimento</div>',
            unsafe_allow_html=True
        )

        if current:
            patient_name = html.escape(current["patient_name"])
            registration = html.escape(current["registration"])
            room = html.escape(current["room"])
            called_at = html.escape(current["called_at"] or "—")

            st.markdown(
                f'<div class="big-name" style="margin-top:20px">{patient_name}</div>',
                unsafe_allow_html=True
            )

            st.markdown(
                f'<div class="big-reg">Matrícula: <b>{registration}</b></div>',
                unsafe_allow_html=True
            )

            st.markdown(
                f'<div style="display:inline-block;margin-top:20px;'
                f'background:#e8f4ff;color:#15517b;border-radius:999px;'
                f'padding:12px 22px;font-size:20px;font-weight:800">'
                f'➡️ {room}</div>',
                unsafe_allow_html=True
            )

            st.markdown(
                f'<p class="muted" style="margin-top:18px">'
                f'Chamado às {called_at}</p>',
                unsafe_allow_html=True
            )

            # Reproduzir o som apenas quando houver uma nova chamada
            # ou quando a hora da chamada mudar (ex.: rechamada).
            event_key = f'{current["id"]}:{current["called_at"] or ""}'
            last_event = st.session_state.get("tv_last_sound_event")

            if event_key != last_event:
                sound_widget(
                    current["id"],
                    current["patient_name"],
                    current["registration"],
                    current["room"]
                )
                st.session_state["tv_last_sound_event"] = event_key

        else:
            st.markdown(
                '<div class="big-name" style="margin-top:24px">'
                'Aguardando chamada…</div>'
                '<p class="muted">O próximo paciente aparecerá aqui.</p>',
                unsafe_allow_html=True
            )

        st.markdown('</div>', unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("Na fila", len(waiting))

        with c2:
            st.metric(
                "Status",
                "Em atendimento" if current else "Aguardando"
            )

        with c3:
            st.metric("Atualizado", datetime.now().strftime("%H:%M:%S"))

        st.caption("Painel sincronizado automaticamente a cada 2 segundos.")

    renderizar_painel_tv()

else:
    st.markdown(
        '<div class="panel"><div class="kicker">Histórico recente</div>',
        unsafe_allow_html=True
    )
    recent = get_recent(30)

    if recent:
        import pandas as pd

        df = pd.DataFrame([{
            "Paciente": r["patient_name"],
            "Matrícula": r["registration"],
            "Destino": r["room"],
            "Status": status_label(r["status"]),
            "Entrada na fila": r["created_at"],
            "Hora da chamada": r["called_at"] or "—",
        } for r in recent])

        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Ainda não há atendimentos no histórico.")

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="panel"><div class="kicker">Configurações de demonstração</div>'
        '<p class="muted">A limpeza apaga a fila e o histórico deste banco de teste.</p>',
        unsafe_allow_html=True
    )

    confirm = st.checkbox(
        "Confirmo que quero apagar todos os dados de demonstração"
    )

    if st.button("🗑️ Limpar dados de teste", disabled=not confirm):
        reset_demo()
        st.success("Dados de demonstração removidos.")
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    '<div style="text-align:center;color:#94a3b8;font-size:12px;padding:18px 0">'
    'Chama Clínica • Protótipo para testes • Não usar para dados reais de saúde'
    '</div>',
    unsafe_allow_html=True
)

