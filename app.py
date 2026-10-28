import html
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from streamlit_autorefresh import st_autorefresh

APP_TITLE = "Chama Clínica"
LOCAL_DB_PATH = os.environ.get("CLINICA_DB_PATH", "clinica.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🔔",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _build_engine() -> Engine:
    """Cria o engine local ou remoto.

    No Streamlit Cloud, configure DATABASE_URL com um PostgreSQL gerenciado.
    SQLite local é mantido para desenvolvimento e uso em uma única instância.
    """
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://") :]
        return create_engine(url, pool_pre_ping=True, future=True)

    db_path = Path(LOCAL_DB_PATH).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )


@st.cache_resource
def get_engine() -> Engine:
    return _build_engine()


engine = get_engine()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return value


def _column_names() -> set[str]:
    return {col["name"] for col in inspect(engine).get_columns("calls")}


def init_db() -> None:
    id_definition = "SERIAL PRIMARY KEY" if engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    id {id_definition},
                    patient_name VARCHAR(100) NOT NULL,
                    registration VARCHAR(40) NOT NULL,
                    room VARCHAR(60) NOT NULL DEFAULT 'Consultório',
                    status VARCHAR(20) NOT NULL DEFAULT 'aguardando',
                    created_at VARCHAR(40) NOT NULL,
                    called_at VARCHAR(40),
                    updated_at VARCHAR(40) NOT NULL
                )
                """.format(id_definition=id_definition)
            )
        )

    # Migração compatível com o banco enviado originalmente.
    columns = _column_names()
    with engine.begin() as conn:
        if "updated_at" not in columns:
            conn.execute(text("ALTER TABLE calls ADD COLUMN updated_at VARCHAR(40)"))
            conn.execute(
                text("UPDATE calls SET updated_at = COALESCE(called_at, created_at)")
            )
        if "room" not in columns:
            conn.execute(
                text("ALTER TABLE calls ADD COLUMN room VARCHAR(60) DEFAULT 'Consultório'")
            )

        # Evita mais de um atendimento ativo mesmo quando há chamadas simultâneas.
        if engine.dialect.name == "sqlite":
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_call "
                    "ON calls(status) WHERE status = 'chamado'"
                )
            )
        elif engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_call "
                    "ON calls(status) WHERE status = 'chamado'"
                )
            )


try:
    init_db()
except SQLAlchemyError as exc:
    st.error(
        "Não foi possível conectar ao banco de dados. "
        "Em produção, configure DATABASE_URL com um PostgreSQL compartilhado."
    )
    st.exception(exc)
    st.stop()


@contextmanager
def transaction():
    with engine.begin() as conn:
        yield conn


def get_current() -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM calls WHERE status = 'chamado' ORDER BY id DESC LIMIT 1")
        ).mappings().first()
        return dict(row) if row else None


def get_waiting() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM calls WHERE status = 'aguardando' ORDER BY id ASC")
        ).mappings().all()
        return [dict(row) for row in rows]


def get_recent(limit: int = 30) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM calls "
                "WHERE status IN ('chamado', 'finalizado', 'cancelado') "
                "ORDER BY id DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]


def get_last_update() -> str | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT MAX(updated_at) FROM calls")).scalar_one_or_none()


def add_patient(name: str, registration: str, room: str) -> None:
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO calls "
                "(patient_name, registration, room, status, created_at, updated_at) "
                "VALUES (:name, :registration, :room, 'aguardando', :created, :updated)"
            ),
            {
                "name": name.strip(),
                "registration": registration.strip(),
                "room": room.strip() or "Consultório",
                "created": timestamp,
                "updated": timestamp,
            },
        )


def _promote_waiting(conn, call_id: int | None = None) -> bool:
    """Finaliza o ativo e promove exatamente um paciente dentro da transação."""
    timestamp = now_iso()
    if engine.dialect.name == "postgresql":
        active_lock = " FOR UPDATE"
        waiting_lock = " FOR UPDATE"
    else:
        active_lock = ""
        waiting_lock = ""

    # A transação impede estados intermediários visíveis ao outro painel.
    conn.execute(
        text("UPDATE calls SET status = 'finalizado', updated_at = :updated "
             "WHERE status = 'chamado'"),
        {"updated": timestamp},
    )
    if call_id is None:
        row = conn.execute(
            text(
                "SELECT id FROM calls WHERE status = 'aguardando' "
                f"ORDER BY id ASC LIMIT 1{waiting_lock}"
            )
        ).first()
    else:
        row = conn.execute(
            text(
                "SELECT id FROM calls WHERE id = :id AND status = 'aguardando' "
                f"LIMIT 1{waiting_lock}"
            ),
            {"id": int(call_id)},
        ).first()

    if not row:
        return False

    updated = conn.execute(
        text(
            "UPDATE calls SET status = 'chamado', called_at = :called, updated_at = :updated "
            "WHERE id = :id AND status = 'aguardando'"
        ),
        {"called": timestamp, "updated": timestamp, "id": int(row.id)},
    )
    if updated.rowcount != 1:
        raise RuntimeError("O paciente selecionado mudou de estado; tente novamente.")
    return True


def call_next() -> bool:
    with transaction() as conn:
        return _promote_waiting(conn)


def call_specific(call_id: int) -> bool:
    with transaction() as conn:
        return _promote_waiting(conn, call_id)


def recall(call_id: int) -> bool:
    timestamp = now_iso()
    with transaction() as conn:
        result = conn.execute(
            text(
                "UPDATE calls SET called_at = :called, updated_at = :updated "
                "WHERE id = :id AND status = 'chamado'"
            ),
            {"called": timestamp, "updated": timestamp, "id": int(call_id)},
        )
        return result.rowcount == 1


def mark_done(call_id: int) -> bool:
    with transaction() as conn:
        result = conn.execute(
            text(
                "UPDATE calls SET status = 'finalizado', updated_at = :updated "
                "WHERE id = :id AND status = 'chamado'"
            ),
            {"updated": now_iso(), "id": int(call_id)},
        )
        return result.rowcount == 1


def cancel_waiting(call_id: int) -> bool:
    with transaction() as conn:
        result = conn.execute(
            text(
                "UPDATE calls SET status = 'cancelado', updated_at = :updated "
                "WHERE id = :id AND status = 'aguardando'"
            ),
            {"updated": now_iso(), "id": int(call_id)},
        )
        return result.rowcount == 1


def reset_demo() -> None:
    with transaction() as conn:
        conn.execute(text("DELETE FROM calls"))


def sound_widget(event_token: str, patient_name: str, room: str) -> None:
    """Aviso com ativação explícita para respeitar bloqueio de autoplay."""
    safe_token = json.dumps(event_token)
    safe_name = json.dumps(patient_name)
    safe_room = json.dumps(room)
    components.html(
        f"""
        <div id="sound-box" style="font:13px Arial;color:#52667c">
          <button id="enable-sound" style="border:1px solid #b8c7d8;border-radius:8px;padding:7px 12px;background:#fff;cursor:pointer">
            Ativar som da TV
          </button>
          <span id="sound-status" style="margin-left:8px">O navegador pode exigir uma interação.</span>
        </div>
        <script>
        (() => {{
          const token = {safe_token};
          const name = {safe_name};
          const room = {safe_room};
          const lastKey = 'chama_clinica_last_event';
          const enabledKey = 'chama_clinica_sound_enabled';
          const status = document.getElementById('sound-status');
          const button = document.getElementById('enable-sound');
          function speakAndBeep() {{
            try {{
              const Ctx = window.AudioContext || window.webkitAudioContext;
              const ctx = new Ctx();
              const play = () => [880, 1175, 880].forEach((freq, i) => {{
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                const at = ctx.currentTime + i * 0.22;
                osc.frequency.value = freq; osc.type = 'sine';
                gain.gain.setValueAtTime(0.0001, at);
                gain.gain.exponentialRampToValueAtTime(0.18, at + 0.03);
                gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.18);
                osc.connect(gain); gain.connect(ctx.destination);
                osc.start(at); osc.stop(at + 0.2);
              }});
              if (ctx.state === 'suspended') ctx.resume().then(play); else play();
              if ('speechSynthesis' in window) {{
                setTimeout(() => {{
                  const u = new SpeechSynthesisUtterance('Paciente ' + name + '. Dirija-se ao ' + room);
                  u.lang = 'pt-BR'; u.rate = 0.92;
                  window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
                }}, 750);
              }}
              localStorage.setItem(lastKey, token);
              status.textContent = 'Som ativado';
            }} catch (error) {{ status.textContent = 'Som bloqueado pelo navegador'; }}
          }}
          button.addEventListener('click', () => {{
            localStorage.setItem(enabledKey, '1'); speakAndBeep();
          }});
          if (localStorage.getItem(enabledKey) === '1' && localStorage.getItem(lastKey) !== token) speakAndBeep();
          if (localStorage.getItem(enabledKey) === '1') status.textContent = 'Som ativado';
        }})();
        </script>
        """,
        height=42,
    )


def status_label(status: str) -> str:
    return {
        "aguardando": "Aguardando",
        "chamado": "Chamado",
        "finalizado": "Finalizado",
        "cancelado": "Cancelado",
    }.get(status, status)


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
    .stApp { background:linear-gradient(135deg,#f4f7fb 0%,#eef3f9 100%); }
    .block-container { padding-top:1.5rem; max-width:1250px; }
    .hero { background:linear-gradient(120deg,#10243a,#1d4668); padding:26px 30px; border-radius:22px; color:white; margin-bottom:22px; box-shadow:0 12px 28px rgba(16,36,58,.13); }
    .hero h1 { font-size:30px; line-height:1.15; margin:0 0 8px; font-weight:800; }
    .hero p { margin:0; color:#d5e4f3; font-size:14px; }
    .panel { background:white; border:1px solid #e1e8f0; border-radius:18px; padding:22px; box-shadow:0 6px 18px rgba(28,50,77,.045); margin-bottom:16px; }
    .muted { color:#64748b; font-size:13px; }
    .big-name { font-size:clamp(28px,4vw,46px); font-weight:800; line-height:1.1; color:#12263a; overflow-wrap:anywhere; }
    .big-reg { font-size:18px; color:#52667c; margin-top:10px; }
    .kicker { font-size:11px; font-weight:800; letter-spacing:1.5px; color:#64819c; text-transform:uppercase; }
    div.stButton > button { border-radius:12px; font-weight:700; min-height:44px; }
    div[data-testid="stForm"] { border:0; padding:0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero">
      <h1>🔔 {APP_TITLE}</h1>
      <p>Chamada de pacientes com sincronização entre médica e TV</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("Navegação")
    view = st.radio("Escolha a tela", ["Painel da médica", "Tela da recepção / TV", "Histórico e configurações"])
    st.divider()
    st.caption("Use um banco PostgreSQL compartilhado em produção.")

if view == "Painel da médica":
    current = get_current()
    waiting = get_waiting()
    col1, col2 = st.columns([1.05, 1.2], gap="large")
    with col1:
        st.markdown('<div class="panel"><div class="kicker">Atendimento atual</div>', unsafe_allow_html=True)
        if current:
            st.markdown(
                f'<div class="big-name">{html.escape(current["patient_name"])}</div>'
                f'<div class="big-reg">Matrícula: <b>{html.escape(current["registration"])}</b></div>'
                f'<p class="muted">Local: {html.escape(current["room"])} • Chamado às {format_datetime(current["called_at"])}</p>',
                unsafe_allow_html=True,
            )
            a, b = st.columns(2)
            with a:
                if st.button("✓ Finalizar atendimento", use_container_width=True):
                    mark_done(current["id"]); st.rerun()
            with b:
                if st.button("🔔 Rechamar paciente", use_container_width=True):
                    if recall(current["id"]):
                        st.success("Paciente rechamado."); st.rerun()
                    else:
                        st.warning("O atendimento já não está ativo."); st.rerun()
        else:
            st.markdown('<div class="big-name">Nenhum paciente chamado</div><p class="muted">Use “Chamar próximo” ou selecione alguém da fila.</p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        if st.button("▶️ Chamar próximo da fila", type="primary", use_container_width=True, disabled=not waiting):
            if call_next(): st.success("Próximo paciente chamado!"); st.rerun()
        st.caption(f"Pacientes aguardando: **{len(waiting)}**")

    with col2:
        st.markdown('<div class="panel"><div class="kicker">Adicionar paciente à fila</div>', unsafe_allow_html=True)
        with st.form("add_patient_form", clear_on_submit=True):
            name = st.text_input("Nome do paciente", max_chars=100)
            registration = st.text_input("Matrícula / identificação", max_chars=40)
            room = st.text_input("Consultório / destino", value="Consultório 1", max_chars=60)
            submitted = st.form_submit_button("＋ Adicionar à fila", use_container_width=True)
            if submitted:
                if not name.strip() or not registration.strip():
                    st.error("Preencha o nome e a matrícula.")
                else:
                    add_patient(name, registration, room); st.success(f"{name.strip()} adicionado(a) à fila."); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel"><div class="kicker">Fila de espera</div>', unsafe_allow_html=True)
        if waiting:
            for i, patient in enumerate(waiting, start=1):
                with st.container(border=True):
                    x, y = st.columns([3, 1])
                    with x:
                        st.markdown(f'**{i}. {html.escape(patient["patient_name"])}**')
                        st.caption(f'Matrícula: {html.escape(patient["registration"])} · {html.escape(patient["room"])}')
                    with y:
                        if st.button("Chamar", key=f'call_{patient["id"]}', use_container_width=True):
                            if call_specific(patient["id"]): st.rerun()
                            else: st.warning("O paciente não está mais aguardando.")
        else:
            st.info("A fila está vazia. Adicione um paciente para começar.")
        st.markdown('</div>', unsafe_allow_html=True)

elif view == "Tela da recepção / TV":
    # Atualização real do fragmento inteiro, consultando o banco compartilhado a cada 2s.
    st_autorefresh(interval=2000, limit=None, key="tv_refresh")
    current = get_current()
    waiting = get_waiting()
    last_update = get_last_update()

    st.markdown('<div class="panel" style="text-align:center;padding:36px 24px"><div class="kicker">Atenção • Atendimento atual</div>', unsafe_allow_html=True)
    if current:
        st.markdown(f'<div class="big-name" style="margin-top:20px">{html.escape(current["patient_name"])}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-reg">Matrícula: <b>{html.escape(current["registration"])}</b></div>', unsafe_allow_html=True)
        st.markdown(f'<div style="display:inline-block;margin-top:20px;background:#e8f4ff;color:#15517b;border-radius:999px;padding:12px 22px;font-size:20px;font-weight:800">➡️ {html.escape(current["room"])}</div>', unsafe_allow_html=True)
        st.markdown(f'<p class="muted" style="margin-top:18px">Chamado às {format_datetime(current["called_at"])}</p>', unsafe_allow_html=True)
        event_token = f'{current["id"]}:{current["called_at"] or ""}'
        sound_widget(event_token, current["patient_name"], current["room"])
    else:
        st.markdown('<div class="big-name" style="margin-top:24px">Aguardando chamada…</div><p class="muted">O próximo paciente aparecerá aqui.</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Na fila", len(waiting))
    with c2: st.metric("Status", "Em atendimento" if current else "Aguardando")
    with c3: st.metric("Última atualização", format_datetime(last_update))
    st.caption("Painel sincronizado automaticamente a cada 2 segundos com o banco configurado.")

else:
    st.markdown('<div class="panel"><div class="kicker">Histórico recente</div>', unsafe_allow_html=True)
    recent = get_recent()
    if recent:
        import pandas as pd
        st.dataframe(pd.DataFrame([{
            "Paciente": row["patient_name"], "Matrícula": row["registration"], "Destino": row["room"],
            "Status": status_label(row["status"]), "Entrada na fila": format_datetime(row["created_at"]),
            "Hora da chamada": format_datetime(row["called_at"]), "Última alteração": format_datetime(row["updated_at"]),
        } for row in recent]), use_container_width=True, hide_index=True)
    else:
        st.info("Ainda não há atendimentos no histórico.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="kicker">Configurações</div><p class="muted">A limpeza apaga a fila e o histórico deste banco.</p>', unsafe_allow_html=True)
    confirm = st.checkbox("Confirmo que quero apagar todos os dados")
    if st.button("🗑️ Limpar dados", disabled=not confirm):
        reset_demo(); st.success("Dados removidos."); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div style="text-align:center;color:#94a3b8;font-size:12px;padding:18px 0">Chama Clínica • Não usar com dados reais de saúde sem controles de segurança adequados</div>', unsafe_allow_html=True)
