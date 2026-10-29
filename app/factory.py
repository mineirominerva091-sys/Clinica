from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from secrets import compare_digest

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

from .models import Call, CallStatus, db, utcnow

load_dotenv()


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///clinica_local.db")
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True, template_folder="../templates", static_folder="../static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_DATABASE_URI=database_url(),
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", ""),
        TV_TOKEN=os.getenv("TV_TOKEN", ""),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    def require_admin(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin_authenticated"):
                if request.path.startswith("/api/"):
                    return jsonify(error="Não autenticado."), 401
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    def tv_token_valid() -> bool:
        configured = app.config.get("TV_TOKEN", "")
        supplied = request.args.get("token") or request.headers.get("X-TV-Token") or session.get("tv_token") or request.cookies.get("tv_token")
        return bool(configured and supplied and compare_digest(str(supplied), str(configured)))

    def require_tv(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not tv_token_valid():
                return jsonify(error="Token da TV inválido ou ausente."), 401
            session["tv_token"] = request.args.get("token") or request.headers.get("X-TV-Token") or session.get("tv_token")
            return view(*args, **kwargs)

        return wrapped

    def json_error(message: str, status: int = 400):
        return jsonify(ok=False, error=message), status

    def payload() -> dict:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            raise ValueError("JSON inválido.")
        return data

    def get_current() -> Call | None:
        return db.session.execute(
            db.select(Call).where(Call.status == CallStatus.CALLED.value).order_by(Call.id.desc()).limit(1)
        ).scalar_one_or_none()

    def waiting_calls() -> list[Call]:
        return list(
            db.session.execute(
                db.select(Call)
                .where(Call.status == CallStatus.WAITING.value)
                .order_by(Call.created_at.asc(), Call.id.asc())
            ).scalars()
        )

    def promote(call_id: int | None = None) -> Call | None:
        """Promove exatamente um aguardando numa transação e mantém estado consistente."""
        query = db.select(Call).where(Call.status == CallStatus.WAITING.value)
        if call_id is not None:
            query = query.where(Call.id == int(call_id))
        else:
            query = query.order_by(Call.created_at.asc(), Call.id.asc())
        target = db.session.execute(query.limit(1).with_for_update()).scalar_one_or_none()
        if target is None:
            return None

        active = db.session.execute(
            db.select(Call).where(Call.status == CallStatus.CALLED.value).with_for_update()
        ).scalars().all()
        moment = utcnow()
        for current in active:
            current.status = CallStatus.FINISHED.value
            current.updated_at = moment

        target.status = CallStatus.CALLED.value
        target.called_at = moment
        target.updated_at = moment
        db.session.flush()
        return target

    @app.get("/health")
    def health():
        try:
            db.session.execute(db.select(func.count(Call.id))).scalar_one()
            return jsonify(status="ok", database="ok")
        except Exception:
            db.session.rollback()
            return jsonify(status="error", database="unavailable"), 503

    @app.get("/")
    def index():
        return redirect(url_for("medica"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            password = request.form.get("password", "")
            configured = app.config.get("ADMIN_PASSWORD", "")
            if configured and compare_digest(password, configured):
                session.clear()
                session["admin_authenticated"] = True
                return redirect(request.args.get("next") or url_for("medica"))
            return render_template("login.html", error="Senha inválida."), 401
        return render_template("login.html", error=None)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/medica")
    @require_admin
    def medica():
        return render_template("medica.html")

    @app.get("/tv")
    def tv():
        if not tv_token_valid():
            return render_template("tv-access.html"), 401
        response = app.make_response(render_template("tv.html"))
        supplied = request.args.get("token")
        if supplied:
            response.set_cookie("tv_token", supplied, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax", secure=request.is_secure)
        return response

    @app.get("/api/dashboard")
    @require_admin
    def dashboard_api():
        current = get_current()
        waiting = waiting_calls()
        return jsonify(
            current=current.to_dict() if current else None,
            waiting=[call.to_dict() for call in waiting],
            waiting_count=len(waiting),
        )

    @app.get("/api/tv/status")
    @require_tv
    def tv_status_api():
        current = get_current()
        waiting_count = db.session.execute(
            db.select(func.count(Call.id)).where(Call.status == CallStatus.WAITING.value)
        ).scalar_one()
        last_update = db.session.execute(db.select(func.max(Call.updated_at))).scalar_one_or_none()
        return jsonify(
            current=current.to_dict() if current else None,
            waiting_count=waiting_count,
            status="Em atendimento" if current else "Aguardando",
            last_update=last_update.isoformat() if last_update else None,
            server_time=datetime.now(timezone.utc).isoformat(),
        )

    @app.get("/api/history")
    @require_admin
    def history_api():
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        rows = db.session.execute(
            db.select(Call)
            .where(Call.status.in_([CallStatus.CALLED.value, CallStatus.FINISHED.value, CallStatus.CANCELED.value]))
            .order_by(Call.id.desc()).limit(limit)
        ).scalars()
        return jsonify(items=[row.to_dict() for row in rows])

    @app.post("/api/patients")
    @require_admin
    def add_patient_api():
        try:
            data = payload()
            name = str(data.get("patient_name", "")).strip()
            registration = str(data.get("registration", "")).strip()
            room = str(data.get("room", "Consultório")).strip() or "Consultório"
            if not name or not registration:
                return json_error("Nome e matrícula são obrigatórios.")
            if len(name) > 100 or len(registration) > 40 or len(room) > 60:
                return json_error("Um dos campos excede o tamanho permitido.")
            call = Call(patient_name=name, registration=registration, room=room, status=CallStatus.WAITING.value)
            db.session.add(call)
            db.session.commit()
            return jsonify(ok=True, item=call.to_dict()), 201
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return json_error(str(exc))
        except Exception:
            db.session.rollback()
            return json_error("Não foi possível adicionar o paciente.", 500)

    @app.post("/api/calls/next")
    @require_admin
    def call_next_api():
        try:
            call = promote()
            if call is None:
                db.session.rollback()
                return json_error("Não há pacientes aguardando.", 409)
            db.session.commit()
            return jsonify(ok=True, item=call.to_dict())
        except IntegrityError:
            db.session.rollback()
            return json_error("Outra chamada ocorreu ao mesmo tempo. Atualize e tente novamente.", 409)
        except Exception:
            db.session.rollback()
            return json_error("Não foi possível chamar o próximo paciente.", 500)

    @app.post("/api/calls/<int:call_id>/call")
    @require_admin
    def call_specific_api(call_id: int):
        try:
            call = promote(call_id)
            if call is None:
                db.session.rollback()
                return json_error("Paciente não está aguardando ou não existe.", 409)
            db.session.commit()
            return jsonify(ok=True, item=call.to_dict())
        except IntegrityError:
            db.session.rollback()
            return json_error("Outra chamada ocorreu ao mesmo tempo. Atualize e tente novamente.", 409)
        except Exception:
            db.session.rollback()
            return json_error("Não foi possível chamar o paciente.", 500)

    @app.post("/api/calls/<int:call_id>/recall")
    @require_admin
    def recall_api(call_id: int):
        call = db.session.get(Call, call_id)
        if not call or call.status != CallStatus.CALLED.value:
            return json_error("O atendimento não está ativo.", 409)
        call.called_at = utcnow()
        call.updated_at = call.called_at
        db.session.commit()
        return jsonify(ok=True, item=call.to_dict())

    @app.post("/api/calls/<int:call_id>/finish")
    @require_admin
    def finish_api(call_id: int):
        call = db.session.get(Call, call_id)
        if not call or call.status != CallStatus.CALLED.value:
            return json_error("O atendimento não está ativo.", 409)
        call.status = CallStatus.FINISHED.value
        call.updated_at = utcnow()
        db.session.commit()
        return jsonify(ok=True, item=call.to_dict())

    @app.post("/api/calls/<int:call_id>/cancel")
    @require_admin
    def cancel_api(call_id: int):
        call = db.session.get(Call, call_id)
        if not call or call.status != CallStatus.WAITING.value:
            return json_error("O paciente não está aguardando.", 409)
        call.status = CallStatus.CANCELED.value
        call.updated_at = utcnow()
        db.session.commit()
        return jsonify(ok=True, item=call.to_dict())

    @app.delete("/api/data")
    @require_admin
    def reset_api():
        db.session.query(Call).delete()
        db.session.commit()
        return jsonify(ok=True)

    @app.errorhandler(413)
    def too_large(_error):
        return json_error("Requisição muito grande.", 413)

    return app
