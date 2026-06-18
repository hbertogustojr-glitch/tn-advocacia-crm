import hashlib
import hmac
import os
import time
from datetime import datetime
from html import escape
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.legal import User
from app.repositories.attendance_repository import AttendanceRepository


CRM_SESSION_COOKIE = "tn_crm_session"
CRM_SESSION_SECRET = settings.crm_session_secret


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def _verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return hmac.compare_digest(digest.hex(), expected)


def _sign_session(user_id: int) -> str:
    issued_at = str(int(time.time()))
    payload = f"{user_id}:{issued_at}"
    signature = hmac.new(CRM_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
    return f"{payload}:{signature}"


def _session_user_id(raw_cookie: str | None) -> int | None:
    if not raw_cookie:
        return None
    try:
        user_id, issued_at, signature = raw_cookie.split(":", 2)
    except ValueError:
        return None
    payload = f"{user_id}:{issued_at}"
    expected = hmac.new(CRM_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    if int(time.time()) - int(issued_at) > 60 * 60 * 12:
        return None
    return int(user_id)


def _require_crm_access(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    if request.url.path in {"/crm/login", "/crm/criar-conta"}:
        return
    user_id = _session_user_id(request.cookies.get(CRM_SESSION_COOKIE))
    user = AttendanceRepository(db).get_user(user_id) if user_id else None
    if user and user.is_active:
        request.state.crm_user = user
        return
    raise HTTPException(status_code=303, headers={"Location": "/crm/login"})


crm_router = APIRouter(prefix="/crm", tags=["crm"], dependencies=[Depends(_require_crm_access)])


def _h(value: object) -> str:
    if value is None:
        return "-"
    return escape(str(value))


def _current_user(request: Request) -> User | None:
    return getattr(request.state, "crm_user", None)


def _is_lawyer(user: User | None) -> bool:
    return bool(user and user.role in {"lawyer", "attorney", "advogado"})


def _dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d/%m/%Y %H:%M")


def _clip(value: str | None, limit: int = 90) -> str:
    if not value:
        return "-"
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _age_text(started_at: datetime | None) -> str:
    if not started_at:
        return "-"
    delta = datetime.now() - started_at
    total_minutes = max(0, int(delta.total_seconds() // 60))
    if total_minutes < 60:
        return f"{total_minutes} min"
    total_hours = total_minutes // 60
    if total_hours < 24:
        return f"{total_hours} h"
    days = total_hours // 24
    return f"{days} dia" if days == 1 else f"{days} dias"


def _urgency_for_pending(item: dict) -> str:
    text = f"{item.get('reason') or ''}".lower()
    created_at = item.get("created_at")
    due_at = item.get("due_at")
    if any(term in text for term in ["audiencia", "audiência", "prazo", "preso", "urgente", "liminar"]):
        return "urgente"
    if due_at and due_at <= datetime.now():
        return "atencao"
    if created_at and (datetime.now() - created_at).days >= 3:
        return "atencao"
    return "normal"


def _urgency_badge(urgency: str) -> str:
    labels = {
        "urgente": "Urgente",
        "atencao": "Atencao",
        "normal": "Normal",
    }
    return f'<span class="urgency urgency-{escape(urgency)}">{escape(labels.get(urgency, urgency))}</span>'


def _status_badge(status: str) -> str:
    labels = {
        "bot_active": "Bot ativo",
        "waiting_human": "Com humano",
        "open": "Aberta",
        "closed": "Fechada",
        "active": "Ativo",
        "inactive": "Inativo",
        "analysis": "Em analise",
        "documents_pending": "Docs pendentes",
    }
    css = status.replace("_", "-")
    return f'<span class="badge badge-{escape(css)}">{escape(labels.get(status, status))}</span>'


def _layout(title: str, active: str, content: str, current_user: User | None = None) -> str:
    nav_items = [
        ("Visao geral", "/crm", "dashboard"),
        ("Pendencias", "/crm/pendencias", "pending"),
        ("Meu perfil", "/crm/me", "lawyers"),
        ("Conversas", "/crm/conversas", "conversations"),
        ("Clientes", "/crm/clientes", "clients"),
        ("Sair", "/crm/logout", "logout"),
    ]
    nav_html = "\n".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for label, href, key in nav_items
    )
    return f"""
    <!doctype html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)} - TN Advocacia CRM</title>
        <style>
            :root {{
                --ink: #4f493f;
                --muted: #756f66;
                --line: #ddd4c8;
                --surface: #fffaf4;
                --page: #eee8df;
                --brand: #9b8d78;
                --brand-dark: #625849;
                --brand-soft: #e8e1d7;
                --sidebar: #090d10;
                --sidebar-soft: #171c20;
                --cream: #f5f1ea;
                --warn: #8a5a2b;
                --blue: #6d6254;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                font-family: Arial, Helvetica, sans-serif;
                color: var(--ink);
                background: var(--page);
            }}
            .shell {{
                min-height: 100vh;
                display: grid;
                grid-template-columns: 220px 1fr;
            }}
            aside {{
                background: var(--sidebar);
                color: #fff;
                padding: 24px 16px;
                border-right: 1px solid #211f1c;
            }}
            .brand {{
                display: grid;
                grid-template-columns: 54px 1fr;
                align-items: center;
                gap: 12px;
                margin-bottom: 28px;
            }}
            .brand-mark {{
                width: 54px;
                height: 54px;
                display: grid;
                place-items: center;
                border: 1px solid rgba(255,255,255,0.72);
                color: #fff;
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 22px;
                letter-spacing: 0;
                line-height: 1;
            }}
            .brand-name {{
                color: #fff;
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 17px;
                line-height: 1.05;
                letter-spacing: 0;
                text-transform: uppercase;
            }}
            .brand-subtitle {{
                color: #ddd5ca;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 4px;
                margin-top: 6px;
            }}
            nav {{
                display: grid;
                gap: 8px;
            }}
            nav a {{
                color: #e9e4dc;
                text-decoration: none;
                padding: 11px 12px;
                border-radius: 6px;
                font-size: 14px;
            }}
            nav a.active, nav a:hover {{
                background: var(--brand);
                color: #fff;
            }}
            main {{
                padding: 28px 32px 48px;
                min-width: 0;
            }}
            .topbar {{
                display: flex;
                align-items: flex-end;
                justify-content: space-between;
                gap: 16px;
                margin-bottom: 22px;
            }}
            h1 {{
                margin: 0;
                font-size: 28px;
                letter-spacing: 0;
                color: var(--brand-dark);
            }}
            .subtitle {{
                margin: 6px 0 0;
                color: var(--muted);
                font-size: 14px;
            }}
            .grid {{
                display: grid;
                gap: 16px;
            }}
            .metrics {{
                grid-template-columns: repeat(3, minmax(160px, 1fr));
            }}
            .two-cols {{
                grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
                align-items: start;
            }}
            .panel {{
                background: var(--surface);
                border: 1px solid var(--line);
                border-radius: 8px;
                overflow-x: auto;
                box-shadow: 0 10px 24px rgba(73, 62, 49, 0.06);
            }}
            .panel-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                padding: 14px 16px;
                border-bottom: 1px solid var(--line);
                background: #fbf7f1;
            }}
            .panel-title {{
                font-weight: 700;
                font-size: 15px;
            }}
            .metric {{
                padding: 16px;
            }}
            .metric strong {{
                display: block;
                font-size: 28px;
                line-height: 1;
                margin-bottom: 8px;
                color: var(--brand-dark);
            }}
            .metric span {{
                color: var(--muted);
                font-size: 13px;
            }}
            table {{
                width: 100%;
                min-width: 640px;
                border-collapse: collapse;
            }}
            th, td {{
                padding: 12px 14px;
                border-bottom: 1px solid #ebe3d8;
                text-align: left;
                vertical-align: top;
                font-size: 14px;
            }}
            th {{
                color: #645b4f;
                background: #ede5da;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0;
            }}
            tr:last-child td {{ border-bottom: 0; }}
            a {{
                color: var(--brand-dark);
                font-weight: 700;
                text-decoration: none;
            }}
            .muted {{
                color: var(--muted);
                font-size: 13px;
            }}
            .subject {{
                max-width: 340px;
                color: #5d554a;
                line-height: 1.35;
            }}
            .badge {{
                display: inline-block;
                min-width: 74px;
                text-align: center;
                padding: 5px 8px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                background: #e9e1d6;
                color: var(--brand-dark);
            }}
            .badge-waiting-human {{
                background: #f6ead9;
                color: var(--warn);
            }}
            .badge-closed, .badge-inactive {{
                background: #ded7cc;
                color: #625849;
            }}
            .badge-open {{
                background: #e6ded2;
                color: var(--blue);
            }}
            .urgency {{
                display: inline-block;
                min-width: 74px;
                text-align: center;
                padding: 5px 8px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }}
            .urgency-urgente {{
                background: #ead1c8;
                color: #7b2f25;
            }}
            .urgency-atencao {{
                background: #f2e2c8;
                color: #7d5527;
            }}
            .urgency-normal {{
                background: #e7e0d6;
                color: #625849;
            }}
            .toolbar {{
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
                align-items: center;
            }}
            input, select {{
                height: 38px;
                border: 1px solid var(--line);
                border-radius: 6px;
                padding: 0 10px;
                background: #fffdf9;
                color: var(--ink);
                font-size: 14px;
            }}
            label {{
                display: grid;
                gap: 6px;
                color: #6b6256;
                font-size: 12px;
                font-weight: 700;
            }}
            .form-grid {{
                display: grid;
                grid-template-columns: repeat(2, minmax(180px, 1fr));
                gap: 14px;
                padding: 16px;
            }}
            .actions {{
                display: flex;
                gap: 10px;
                padding: 0 16px 16px;
            }}
            button, .button {{
                height: 38px;
                border: 0;
                border-radius: 6px;
                padding: 0 12px;
                background: var(--brand);
                color: #fff;
                font-weight: 700;
                cursor: pointer;
                box-shadow: 0 5px 12px rgba(98, 88, 73, 0.18);
            }}
            button.secondary, .button.secondary {{
                background: var(--sidebar-soft);
            }}
            .timeline {{
                padding: 16px;
                display: grid;
                gap: 12px;
            }}
            .message {{
                border: 1px solid var(--line);
                border-radius: 8px;
                padding: 12px 14px;
                background: #fffdf9;
            }}
            .message.outbound {{
                border-left: 5px solid var(--brand);
            }}
            .message.inbound {{
                border-left: 5px solid var(--sidebar-soft);
            }}
            .message p {{
                margin: 8px 0 0;
                line-height: 1.45;
                white-space: pre-wrap;
            }}
            .details {{
                padding: 16px;
                display: grid;
                gap: 12px;
            }}
            .detail-row {{
                display: flex;
                justify-content: space-between;
                gap: 16px;
                border-bottom: 1px solid #ebe3d8;
                padding-bottom: 10px;
            }}
            .detail-row:last-child {{
                border-bottom: 0;
                padding-bottom: 0;
            }}
            .empty {{
                padding: 18px;
                color: var(--muted);
            }}
            @media (max-width: 820px) {{
                .shell {{ grid-template-columns: 1fr; }}
                aside {{ position: static; }}
                .metrics, .two-cols, .form-grid {{ grid-template-columns: 1fr; }}
                main {{ padding: 20px 14px 36px; }}
                .topbar {{ align-items: flex-start; flex-direction: column; }}
            }}
        </style>
    </head>
    <body>
        <div class="shell">
            <aside>
                <div class="brand">
                    <div class="brand-mark">TN</div>
                    <div>
                        <div class="brand-name">Taciana Nunes</div>
                        <div class="brand-subtitle">ADVOCACIA</div>
                    </div>
                </div>
                <nav>{nav_html}</nav>
            </aside>
            <main>{content}</main>
        </div>
    </body>
    </html>
    """


def _page_header(title: str, subtitle: str) -> str:
    return f"""
    <div class="topbar">
        <div>
            <h1>{escape(title)}</h1>
            <p class="subtitle">{escape(subtitle)}</p>
        </div>
    </div>
    """


def _login_page(
    created: bool = False,
    error: str | None = None,
    email: str = "",
) -> str:
    success_message = (
        '<div class="success">Acesso criado. Entre com seu e-mail e senha.</div>'
        if created
        else ""
    )
    error_message = f'<div class="error">{escape(error)}</div>' if error else ""
    registration_link = (
        '<a class="secondary-link" href="/crm/criar-conta">Criar acesso</a>'
        if settings.crm_self_registration_enabled
        else ""
    )
    return f"""
    <!doctype html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Entrar - TN Advocacia CRM</title>
        <style>
            body {{
                margin: 0;
                min-height: 100vh;
                display: grid;
                place-items: center;
                font-family: Arial, Helvetica, sans-serif;
                background: #090d10;
                color: #4f493f;
            }}
            .card {{
                width: min(420px, calc(100vw - 32px));
                background: #fffaf4;
                border: 1px solid #ddd4c8;
                border-radius: 8px;
                padding: 24px;
            }}
            .brand {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 22px;
            }}
            .mark {{
                width: 52px;
                height: 52px;
                display: grid;
                place-items: center;
                border: 1px solid #625849;
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 22px;
                color: #625849;
            }}
            h1 {{ margin: 0; font-size: 24px; color: #625849; }}
            p {{ color: #756f66; margin: 6px 0 20px; }}
            label {{ display: grid; gap: 6px; margin-bottom: 14px; font-weight: 700; font-size: 13px; }}
            input {{
                height: 42px;
                border: 1px solid #ddd4c8;
                border-radius: 6px;
                padding: 0 10px;
                background: #fffdf9;
                font-size: 15px;
            }}
            button {{
                width: 100%;
                height: 42px;
                border: 0;
                border-radius: 6px;
                background: #9b8d78;
                color: white;
                font-weight: 700;
                cursor: pointer;
            }}
            .secondary-link {{
                display: grid;
                place-items: center;
                height: 42px;
                margin-top: 10px;
                border: 1px solid #9b8d78;
                border-radius: 6px;
                color: #625849;
                text-decoration: none;
                font-weight: 700;
            }}
            .success {{
                margin-bottom: 16px;
                padding: 10px;
                border: 1px solid #9b8d78;
                border-radius: 6px;
                background: #f1ebe2;
                font-size: 13px;
            }}
            .error {{
                margin-bottom: 16px;
                padding: 10px;
                border: 1px solid #c99b8b;
                border-radius: 6px;
                background: #ead1c8;
                color: #7b2f25;
                font-size: 13px;
            }}
        </style>
    </head>
    <body>
        <form class="card" method="post" action="/crm/login">
            <div class="brand">
                <div class="mark">TN</div>
                <div>
                    <h1>Entrar no CRM</h1>
                    <p>TN Advocacia</p>
                </div>
            </div>
            {error_message}
            <label>E-mail
                <input type="email" name="email" value="{escape(email)}" required autofocus>
            </label>
            <label>Senha
                <input type="password" name="password" required>
            </label>
            {success_message}
            <button type="submit">Entrar</button>
            {registration_link}
        </form>
    </body>
    </html>
    """


@crm_router.get("/login", response_class=HTMLResponse)
def crm_login_page(created: bool = Query(default=False)) -> str:
    return _login_page(created=created)


def _registration_page(error: str | None = None) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    return f"""
    <!doctype html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Criar acesso - TN Advocacia CRM</title>
        <style>
            body {{
                margin: 0;
                min-height: 100vh;
                display: grid;
                place-items: center;
                padding: 24px 0;
                font-family: Arial, Helvetica, sans-serif;
                background: #090d10;
                color: #4f493f;
            }}
            .card {{
                width: min(440px, calc(100vw - 32px));
                background: #fffaf4;
                border: 1px solid #ddd4c8;
                border-radius: 8px;
                padding: 24px;
            }}
            .brand {{ display: flex; align-items: center; gap: 12px; margin-bottom: 22px; }}
            .mark {{
                width: 52px; height: 52px; display: grid; place-items: center;
                border: 1px solid #625849; font-family: Georgia, 'Times New Roman', serif;
                font-size: 22px; color: #625849;
            }}
            h1 {{ margin: 0; font-size: 24px; color: #625849; }}
            p {{ color: #756f66; margin: 6px 0 20px; }}
            label {{ display: grid; gap: 6px; margin-bottom: 14px; font-weight: 700; font-size: 13px; }}
            input {{
                height: 42px; border: 1px solid #ddd4c8; border-radius: 6px;
                padding: 0 10px; background: #fffdf9; font-size: 15px;
            }}
            button {{
                width: 100%; height: 42px; border: 0; border-radius: 6px;
                background: #9b8d78; color: white; font-weight: 700; cursor: pointer;
            }}
            .back {{
                display: block; margin-top: 14px; text-align: center;
                color: #625849; font-weight: 700; text-decoration: none;
            }}
            .error {{
                margin-bottom: 14px; padding: 10px; border-radius: 6px;
                background: #ead1c8; color: #7b2f25; font-size: 13px;
            }}
        </style>
    </head>
    <body>
        <form class="card" method="post" action="/crm/criar-conta">
            <div class="brand">
                <div class="mark">TN</div>
                <div>
                    <h1>Criar acesso</h1>
                    <p>Cadastro de advogado</p>
                </div>
            </div>
            {error_html}
            <label>Nome completo
                <input name="full_name" required autofocus>
            </label>
            <label>E-mail
                <input type="email" name="email" required>
            </label>
            <label>Senha
                <input type="password" name="password" minlength="6" required>
            </label>
            <label>Confirmar senha
                <input type="password" name="password_confirmation" minlength="6" required>
            </label>
            <button type="submit">Criar meu acesso</button>
            <a class="back" href="/crm/login">Voltar para o login</a>
        </form>
    </body>
    </html>
    """


@crm_router.get("/criar-conta", response_class=HTMLResponse)
def crm_registration_page() -> str:
    if not settings.crm_self_registration_enabled:
        raise HTTPException(status_code=404, detail="Cadastro de acesso desativado.")
    return _registration_page()


@crm_router.post("/criar-conta", response_model=None)
async def crm_create_account(
    request: Request,
    db: Session = Depends(get_db),
):
    if not settings.crm_self_registration_enabled:
        raise HTTPException(status_code=404, detail="Cadastro de acesso desativado.")
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body)
    full_name = form.get("full_name", [""])[0].strip()
    email = form.get("email", [""])[0].strip().lower()
    password = form.get("password", [""])[0]
    password_confirmation = form.get("password_confirmation", [""])[0]
    if not full_name or not email:
        return HTMLResponse(_registration_page("Nome e e-mail sao obrigatorios."), status_code=400)
    if len(password) < 6:
        return HTMLResponse(_registration_page("A senha precisa ter pelo menos 6 caracteres."), status_code=400)
    if password != password_confirmation:
        return HTMLResponse(_registration_page("As senhas nao conferem."), status_code=400)

    repository = AttendanceRepository(db)
    if repository.get_user_by_email(email):
        return HTMLResponse(_registration_page("Este e-mail ja possui acesso."), status_code=400)
    repository.create_lawyer(
        organization_id=settings.default_organization_id,
        full_name=full_name,
        email=email,
        password_hash=_hash_password(password),
    )
    db.commit()
    return RedirectResponse("/crm/login?created=true", status_code=303)


@crm_router.post("/login", response_model=None)
async def crm_login(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body)
    email = form.get("email", [""])[0]
    password = form.get("password", [""])[0]
    repository = AttendanceRepository(db)
    user = repository.get_user_by_email(email)
    if not user or not user.is_active or not _verify_password(password, user.password_hash):
        return HTMLResponse(
            _login_page(
                error="E-mail ou senha invalidos. Tente novamente.",
                email=email,
            ),
            status_code=401,
        )
    response = RedirectResponse("/crm", status_code=303)
    response.set_cookie(
        CRM_SESSION_COOKIE,
        _sign_session(user.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@crm_router.get("/logout")
def crm_logout() -> RedirectResponse:
    response = RedirectResponse("/crm/login", status_code=303)
    response.delete_cookie(CRM_SESSION_COOKIE)
    return response


@crm_router.get("/me")
def crm_my_profile(request: Request) -> RedirectResponse:
    current_user = _current_user(request)
    if _is_lawyer(current_user):
        return RedirectResponse(f"/crm/advogados/{current_user.id}/pendencias", status_code=303)
    return RedirectResponse("/crm/advogados", status_code=303)


@crm_router.get("", response_class=HTMLResponse)
@crm_router.get("/", response_class=HTMLResponse)
def crm_home(request: Request, db: Session = Depends(get_db)) -> str:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    lawyer_view = _is_lawyer(current_user)
    assigned_user_id = current_user.id if lawyer_view and current_user else None
    stats = repository.crm_stats(settings.default_organization_id)
    recent = repository.list_crm_conversations(
        settings.default_organization_id,
        assigned_user_id=assigned_user_id,
        limit=8,
    )
    handoffs = repository.list_open_handoffs(limit=8, assigned_user_id=assigned_user_id)
    pending_count = len(repository.list_pending_queue(settings.default_organization_id, assigned_user_id=assigned_user_id))

    metrics = "".join(
        f"""
        <section class="panel metric">
            <strong>{value}</strong>
            <span>{label}</span>
        </section>
        """
        for label, value in (
            [
                ("Minhas pendencias", pending_count),
                ("Minhas conversas", len(recent)),
                ("Meus encaminhamentos", len(handoffs)),
            ]
            if lawyer_view
            else [
                ("Conversas totais", stats["conversations"]),
                ("Conversas ativas", stats["active_conversations"]),
                ("Precisam de humano", stats["waiting_human"]),
                ("Clientes/contatos", stats["contacts"]),
                ("Encaminhamentos abertos", stats["open_handoffs"]),
                ("Follow-ups agendados", stats["scheduled_followups"]),
            ]
        )
    )
    recent_rows = _conversation_rows(recent)
    handoff_rows = "\n".join(
        f"""
        <tr>
            <td><a href="/crm/conversas/{conversation.id}">#{conversation.id}</a></td>
            <td>{_h(contact.display_name)}</td>
            <td>{_h(handoff.reason)}</td>
        </tr>
        """
        for handoff, conversation, contact in handoffs
    )
    content = (
        _page_header(
            "Visao geral" if not lawyer_view else f"Painel de {current_user.full_name}",
            "Acompanhamento rapido do atendimento do WhatsApp."
            if not lawyer_view
            else "Resumo dos atendimentos encaminhados para voce.",
        )
        + f"""
        <div class="grid metrics">{metrics}</div>
        <div class="grid two-cols" style="margin-top: 18px;">
            <section class="panel">
                <div class="panel-header">
                    <div class="panel-title">Conversas recentes</div>
                    <a href="/crm/conversas">ver todas</a>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Conversa</th>
                            <th>Contato</th>
                            <th>Assunto</th>
                            <th>Status</th>
                            <th>Mensagens</th>
                            <th>Ultima mensagem</th>
                        </tr>
                    </thead>
                    <tbody>{recent_rows or '<tr><td colspan="6" class="empty">Nenhuma conversa encontrada.</td></tr>'}</tbody>
                </table>
            </section>
            <section class="panel">
                <div class="panel-header">
                    <div class="panel-title">Encaminhamentos</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Conversa</th>
                            <th>Contato</th>
                            <th>Motivo</th>
                        </tr>
                    </thead>
                    <tbody>{handoff_rows or '<tr><td colspan="3" class="empty">Nenhum encaminhamento aberto.</td></tr>'}</tbody>
                </table>
            </section>
        </div>
        """
    )
    return _layout("Visao geral", "dashboard", content, current_user)


@crm_router.get("/pendencias", response_class=HTMLResponse)
def crm_pending_queue(request: Request, db: Session = Depends(get_db)) -> str:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    lawyer_view = _is_lawyer(current_user)
    pending_items = repository.list_pending_queue(
        settings.default_organization_id,
        assigned_user_id=current_user.id if lawyer_view and current_user else None,
    )
    lawyers = [] if lawyer_view else repository.list_lawyers(settings.default_organization_id)
    ordered_items = sorted(
        pending_items,
        key=lambda item: (
            {"urgente": 0, "atencao": 1, "normal": 2}[_urgency_for_pending(item)],
            item.get("created_at") or datetime.now(),
        ),
    )
    rows = "\n".join(_pending_row(item, lawyers=lawyers) for item in ordered_items)
    content = (
        _page_header(
            "Minhas pendencias" if lawyer_view else "Pendencias",
            "Atendimentos encaminhados para voce."
            if lawyer_view
            else "Fila de encaminhamentos e acompanhamentos que precisam de atencao humana.",
        )
        + f"""
        <section class="panel">
            <div class="panel-header">
                <div class="panel-title">{"Minha fila" if lawyer_view else "Fila do escritorio"}</div>
                <span class="muted">{len(ordered_items)} pendencia(s) aberta(s)</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Urgencia</th>
                        <th>Cliente</th>
                        <th>Pendencia</th>
                        <th>Aberta ha</th>
                        <th>Ultima interacao</th>
                        <th>Acoes</th>
                    </tr>
                </thead>
                <tbody>{rows or '<tr><td colspan="6" class="empty">Nenhuma pendencia aberta.</td></tr>'}</tbody>
            </table>
        </section>
        """
    )
    return _layout("Pendencias", "pending", content, current_user)


@crm_router.get("/advogados", response_class=HTMLResponse)
def crm_lawyers(request: Request, db: Session = Depends(get_db)):
    current_user = _current_user(request)
    if _is_lawyer(current_user):
        return RedirectResponse(f"/crm/advogados/{current_user.id}/pendencias", status_code=303)
    repository = AttendanceRepository(db)
    lawyers = repository.list_lawyers(settings.default_organization_id)
    rows = "\n".join(
        f"""
        <tr>
            <td>
                <strong>{escape(lawyer.full_name)}</strong>
                <div class="muted">{escape(lawyer.email)}</div>
            </td>
            <td>{escape(lawyer.role)}</td>
            <td><a class="button" href="/crm/advogados/{lawyer.id}/pendencias">Entrar no perfil</a></td>
        </tr>
        """
        for lawyer in lawyers
    )
    content = (
        _page_header(
            "Perfis dos advogados",
            "Escolha o perfil do advogado para ver somente as pendencias atribuidas a ele.",
        )
        + f"""
        <section class="panel" style="margin-bottom: 16px;">
            <div class="panel-header">
                <div class="panel-title">Adicionar perfil</div>
            </div>
            <form method="post" action="/crm/advogados">
                <div class="form-grid">
                    <label>Nome do advogado
                        <input name="full_name" placeholder="Ex: Ana Silva" required>
                    </label>
                <label>E-mail
                    <input name="email" type="email" placeholder="ana@escritorio.com" required>
                </label>
                <label>Senha inicial
                    <input name="password" type="password" placeholder="Minimo 6 caracteres" required>
                </label>
            </div>
                <div class="actions">
                    <button type="submit">Adicionar perfil</button>
                </div>
            </form>
        </section>
        <section class="panel">
            <div class="panel-header">
                <div class="panel-title">Advogados cadastrados</div>
                <span class="muted">{len(lawyers)} perfil(is)</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Advogado</th>
                        <th>Tipo</th>
                        <th>Acesso</th>
                    </tr>
                </thead>
                <tbody>{rows or '<tr><td colspan="3" class="empty">Nenhum advogado cadastrado.</td></tr>'}</tbody>
            </table>
        </section>
        """
    )
    return _layout("Perfis dos advogados", "lawyers", content, current_user)


@crm_router.post("/advogados")
async def crm_create_lawyer(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body)
    full_name = form.get("full_name", [""])[0].strip()
    email = form.get("email", [""])[0].strip()
    password = form.get("password", [""])[0]
    if not full_name or not email or len(password) < 6:
        raise HTTPException(status_code=400, detail="Nome, e-mail e senha com no minimo 6 caracteres sao obrigatorios.")
    repository = AttendanceRepository(db)
    repository.create_lawyer(
        organization_id=settings.default_organization_id,
        full_name=full_name,
        email=email,
        password_hash=_hash_password(password),
    )
    db.commit()
    return RedirectResponse("/crm/advogados", status_code=303)


@crm_router.get("/advogados/{lawyer_id}/pendencias", response_class=HTMLResponse)
def crm_lawyer_pending_queue(
    lawyer_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    if _is_lawyer(current_user) and current_user.id != lawyer_id:
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a fila de outro advogado.")
    lawyer = repository.get_user(lawyer_id)
    if not lawyer or lawyer.organization_id != settings.default_organization_id:
        raise HTTPException(status_code=404, detail="Advogado nao encontrado.")
    pending_items = repository.list_pending_queue(
        settings.default_organization_id,
        assigned_user_id=lawyer.id,
    )
    ordered_items = sorted(
        pending_items,
        key=lambda item: (
            {"urgente": 0, "atencao": 1, "normal": 2}[_urgency_for_pending(item)],
            item.get("created_at") or datetime.now(),
        ),
    )
    rows = "\n".join(_pending_row(item, return_to=f"/crm/advogados/{lawyer.id}/pendencias") for item in ordered_items)
    content = (
        _page_header(
            f"Pendencias de {lawyer.full_name}",
            "Fila exclusiva com atendimentos encaminhados para este advogado.",
        )
        + f"""
        <section class="panel">
            <div class="panel-header">
                <div class="panel-title">Fila de {escape(lawyer.full_name)}</div>
                <span class="muted">{len(ordered_items)} pendencia(s) aberta(s)</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Urgencia</th>
                        <th>Cliente</th>
                        <th>Pendencia</th>
                        <th>Aberta ha</th>
                        <th>Ultima interacao</th>
                        <th>Acoes</th>
                    </tr>
                </thead>
                <tbody>{rows or '<tr><td colspan="6" class="empty">Nenhuma pendencia para este advogado.</td></tr>'}</tbody>
            </table>
        </section>
        """
    )
    return _layout(f"Pendencias de {lawyer.full_name}", "lawyers", content, current_user)


@crm_router.post("/pendencias/handoffs/{handoff_id}/resolver")
def crm_resolve_handoff(
    handoff_id: int,
    return_to: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    repository = AttendanceRepository(db)
    handoff = repository.resolve_handoff(handoff_id)
    if not handoff:
        raise HTTPException(status_code=404, detail="Encaminhamento nao encontrado.")
    db.commit()
    safe_return = return_to if return_to and return_to.startswith("/crm/") else "/crm/pendencias"
    return RedirectResponse(safe_return, status_code=303)


@crm_router.post("/pendencias/handoffs/{handoff_id}/atribuir")
async def crm_assign_handoff(
    handoff_id: int,
    request: Request,
    return_to: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body)
    try:
        assigned_user_id = int(form.get("assigned_user_id", [""])[0])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Advogado invalido.") from exc
    repository = AttendanceRepository(db)
    handoff = repository.assign_handoff(handoff_id, assigned_user_id)
    if not handoff:
        raise HTTPException(status_code=404, detail="Pendencia ou advogado nao encontrado.")
    db.commit()
    safe_return = return_to if return_to and return_to.startswith("/crm/") else "/crm/pendencias"
    return RedirectResponse(safe_return, status_code=303)


@crm_router.get("/conversas", response_class=HTMLResponse)
def crm_conversations(
    request: Request,
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> str:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    lawyer_view = _is_lawyer(current_user)
    rows = repository.list_crm_conversations(
        settings.default_organization_id,
        status=status or None,
        query=q or None,
        assigned_user_id=current_user.id if lawyer_view and current_user else None,
    )
    status_options = [
        ("", "Todos"),
        ("bot_active", "Bot ativo"),
        ("waiting_human", "Com humano"),
        ("closed", "Fechada"),
        ("open", "Aberta"),
    ]
    options_html = "".join(
        f'<option value="{escape(value)}" {"selected" if value == (status or "") else ""}>{label}</option>'
        for value, label in status_options
    )
    content = (
        _page_header(
            "Minhas conversas" if lawyer_view else "Conversas",
            "Conversas encaminhadas para voce."
            if lawyer_view
            else "Historico completo das conversas recebidas pelo WhatsApp.",
        )
        + f"""
        <section class="panel">
            <div class="panel-header">
                <form class="toolbar" method="get" action="/crm/conversas">
                    <input type="search" name="q" placeholder="Buscar nome, telefone ou CPF" value="{escape(q or '')}">
                    <select name="status">{options_html}</select>
                    <button type="submit">Filtrar</button>
                    <a class="button secondary" href="/crm/conversas">Limpar</a>
                </form>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Conversa</th>
                        <th>Contato</th>
                        <th>Assunto</th>
                        <th>Status</th>
                        <th>Mensagens</th>
                        <th>Ultima mensagem</th>
                    </tr>
                </thead>
                <tbody>{_conversation_rows(rows) or '<tr><td colspan="6" class="empty">Nenhuma conversa encontrada.</td></tr>'}</tbody>
            </table>
        </section>
        """
    )
    return _layout("Conversas", "conversations", content, current_user)


@crm_router.get("/conversas/{conversation_id}", response_class=HTMLResponse)
def crm_conversation_detail(
    conversation_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    repository = AttendanceRepository(db)
    matched = repository.get_conversation_with_contact(conversation_id)
    if not matched:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    conversation, contact = matched
    current_user = _current_user(request)
    if _is_lawyer(current_user) and conversation.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a esta conversa.")
    profile = repository.get_contact_profile(contact.id)
    client = profile[1] if profile else None
    messages = repository.list_messages(conversation_id)
    subject = next((message.body for message in messages if message.direction == "inbound"), None)
    message_rows = "\n".join(
        f"""
        <article class="message {escape(message.direction)}">
            <div class="muted">{_h(message.sender_type)} - {_dt(message.sent_at)}</div>
            <p>{escape(message.body)}</p>
        </article>
        """
        for message in messages
    )
    close_action = ""
    if conversation.status != "closed":
        close_action = f"""
        <form method="post" action="/crm/conversas/{conversation.id}/encerrar">
            <button type="submit">Encerrar conversa</button>
        </form>
        """
    content = (
        _page_header(
            f"Conversa #{conversation.id}",
            f"{contact.display_name or 'Contato sem nome'} - {contact.phone_number or '-'}",
        )
        + f"""
        <div class="grid two-cols">
            <section class="panel">
                <div class="panel-header">
                    <div class="panel-title">Mensagens</div>
                    {_status_badge(conversation.status)}
                </div>
                <div class="timeline">{message_rows or '<div class="empty">Nenhuma mensagem encontrada.</div>'}</div>
            </section>
            <aside class="panel" style="background: #fff; color: var(--ink); padding: 0;">
                <div class="panel-header">
                    <div class="panel-title">Ficha rapida</div>
                    <a href="/crm/clientes/{contact.id}">editar</a>
                </div>
                <div class="details">
                    <div class="detail-row"><span>Contato</span><strong>{_h(contact.display_name)}</strong></div>
                    <div class="detail-row"><span>Telefone</span><strong>{_h(contact.phone_number)}</strong></div>
                    <div class="detail-row"><span>Assunto</span><strong>{_h(_clip(subject, 120))}</strong></div>
                    <div class="detail-row"><span>Cliente</span><strong>{_h(client.display_name if client else None)}</strong></div>
                    <div class="detail-row"><span>CPF/CNPJ</span><strong>{_h(client.document_number if client else None)}</strong></div>
                    <div class="detail-row"><span>Status cliente</span><strong>{_h(client.status if client else None)}</strong></div>
                    <div class="detail-row"><span>Criada em</span><strong>{_dt(conversation.created_at)}</strong></div>
                    <div class="detail-row"><span>Atualizada em</span><strong>{_dt(conversation.updated_at)}</strong></div>
                </div>
                <div class="actions">{close_action}<a class="button secondary" href="/crm/conversas">Voltar</a></div>
            </aside>
        </div>
        """
    )
    return _layout(f"Conversa #{conversation.id}", "conversations", content, current_user)


@crm_router.post("/conversas/{conversation_id}/encerrar")
def crm_close_conversation(
    conversation_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    repository = AttendanceRepository(db)
    matched = repository.get_conversation_with_contact(conversation_id)
    current_user = _current_user(request)
    if matched and _is_lawyer(current_user) and matched[0].assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a esta conversa.")
    conversation = repository.close_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    db.commit()
    return RedirectResponse(f"/crm/conversas/{conversation_id}", status_code=303)


@crm_router.get("/clientes", response_class=HTMLResponse)
def crm_clients(
    request: Request,
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> str:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    lawyer_view = _is_lawyer(current_user)
    rows = repository.list_crm_contacts(
        settings.default_organization_id,
        query=q or None,
        assigned_user_id=current_user.id if lawyer_view and current_user else None,
    )
    client_rows = "\n".join(
        f"""
        <tr>
            <td><a href="/crm/clientes/{contact.id}">{_h(client.display_name if client else contact.display_name)}</a></td>
            <td>{_h(contact.phone_number)}</td>
            <td>{_h(client.document_number if client else None)}</td>
            <td>{_status_badge(client.status if client else 'active')}</td>
            <td>{conversation_count}</td>
            <td>{_dt(last_conversation_at)}</td>
        </tr>
        """
        for contact, client, conversation_count, last_conversation_at in rows
    )
    content = (
        _page_header(
            "Meus clientes" if lawyer_view else "Clientes",
            "Clientes com atendimentos encaminhados para voce."
            if lawyer_view
            else "Contatos do WhatsApp vinculados a fichas de cliente.",
        )
        + f"""
        <section class="panel">
            <div class="panel-header">
                <form class="toolbar" method="get" action="/crm/clientes">
                    <input type="search" name="q" placeholder="Buscar nome, telefone ou CPF" value="{escape(q or '')}">
                    <button type="submit">Buscar</button>
                    <a class="button secondary" href="/crm/clientes">Limpar</a>
                </form>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Cliente</th>
                        <th>Telefone</th>
                        <th>CPF/CNPJ</th>
                        <th>Status</th>
                        <th>Conversas</th>
                        <th>Ultima conversa</th>
                    </tr>
                </thead>
                <tbody>{client_rows or '<tr><td colspan="6" class="empty">Nenhum cliente encontrado.</td></tr>'}</tbody>
            </table>
        </section>
        """
    )
    return _layout("Clientes", "clients", content, current_user)


@crm_router.get("/clientes/{contact_id}", response_class=HTMLResponse)
def crm_client_detail(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    repository = AttendanceRepository(db)
    profile = repository.get_contact_profile(contact_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado.")
    contact, client = profile
    current_user = _current_user(request)
    lawyer_view = _is_lawyer(current_user)
    conversations = repository.list_conversations_for_contact(
        contact_id,
        assigned_user_id=current_user.id if lawyer_view and current_user else None,
    )
    if lawyer_view and not conversations:
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a este cliente.")
    matters = repository.list_legal_matters_for_client(client.id) if client else []
    matter_rows = "\n".join(
        f"""
        <tr>
            <td>
                <strong>{_h(matter.title)}</strong>
                <div class="muted">{_h(matter.matter_type)}</div>
            </td>
            <td>{_h(matter.process_number)}</td>
            <td>{_status_badge(matter.status)}</td>
            <td>{_dt(matter.updated_at)}</td>
        </tr>
        """
        for matter in matters
    )
    matter_form = (
        f"""
        <form method="post" action="/crm/clientes/{contact.id}/processos">
            <div class="form-grid">
                <label>Nome do caso/processo
                    <input name="title" placeholder="Ex: Revisao de beneficio" required>
                </label>
                <label>Area/tipo
                    <input name="matter_type" placeholder="Ex: Previdenciario">
                </label>
                <label>Numero do processo
                    <input name="process_number" placeholder="Opcional">
                </label>
                <label>Status
                    <select name="status">
                        <option value="active">Ativo</option>
                        <option value="analysis">Em analise</option>
                        <option value="documents_pending">Documentos pendentes</option>
                        <option value="closed">Encerrado</option>
                    </select>
                </label>
            </div>
            <div class="actions"><button type="submit">Adicionar processo</button></div>
        </form>
        """
        if client
        else '<div class="empty">Salve a ficha do cliente antes de cadastrar processos.</div>'
    )
    pending_items = [
        item
        for item in repository.list_pending_queue(settings.default_organization_id)
        if item["contact"].id == contact_id
    ]
    pending_rows = "\n".join(
        f"""
        <tr>
            <td>{_urgency_badge(_urgency_for_pending(item))}</td>
            <td>{_h(_clip(item.get("reason"), 120))}</td>
            <td>{_age_text(item.get("created_at"))}</td>
            <td><a href="/crm/conversas/{item["conversation"].id}">ver conversa</a></td>
        </tr>
        """
        for item in pending_items
    )
    conversation_rows = "\n".join(
        f"""
        <tr>
            <td><a href="/crm/conversas/{conversation.id}">#{conversation.id}</a></td>
            <td><div class="subject">{_h(_clip(repository.get_conversation_subject(conversation.id)))}</div></td>
            <td>{_status_badge(conversation.status)}</td>
            <td>{_dt(conversation.created_at)}</td>
            <td>{_dt(conversation.updated_at)}</td>
        </tr>
        """
        for conversation in conversations
    )
    status = client.status if client else "active"
    content = (
        _page_header(
            client.display_name if client else contact.display_name or "Cliente",
            "Ficha do cliente e historico de atendimentos.",
        )
        + f"""
        <div class="grid two-cols">
            <section class="panel">
                <div class="panel-header"><div class="panel-title">Dados do cliente</div></div>
                <form method="post" action="/crm/clientes/{contact.id}">
                    <div class="form-grid">
                        <label>Nome no WhatsApp
                            <input name="contact_name" value="{_h(contact.display_name)}">
                        </label>
                        <label>Nome do cliente
                            <input name="client_name" value="{_h(client.display_name if client else contact.display_name)}">
                        </label>
                        <label>Telefone
                            <input value="{_h(contact.phone_number)}" disabled>
                        </label>
                        <label>CPF/CNPJ
                            <input name="document_number" value="{_h(client.document_number if client else None)}">
                        </label>
                        <label>Status
                            <select name="client_status">
                                <option value="active" {"selected" if status == "active" else ""}>Ativo</option>
                                <option value="inactive" {"selected" if status == "inactive" else ""}>Inativo</option>
                            </select>
                        </label>
                    </div>
                    <div class="actions">
                        <button type="submit">Salvar ficha</button>
                        <a class="button secondary" href="/crm/clientes">Voltar</a>
                    </div>
                </form>
            </section>
            <section class="panel">
                <div class="panel-header"><div class="panel-title">Conversas desse cliente</div></div>
                <table>
                    <thead>
                        <tr>
                            <th>Conversa</th>
                            <th>Assunto</th>
                            <th>Status</th>
                            <th>Criada em</th>
                            <th>Atualizada em</th>
                        </tr>
                    </thead>
                    <tbody>{conversation_rows or '<tr><td colspan="5" class="empty">Nenhuma conversa encontrada.</td></tr>'}</tbody>
                </table>
            </section>
        </div>
        <section class="panel" style="margin-top: 16px;">
            <div class="panel-header"><div class="panel-title">Pendencias abertas desse cliente</div></div>
            <table>
                <thead>
                    <tr>
                        <th>Urgencia</th>
                        <th>Pendencia</th>
                        <th>Aberta ha</th>
                        <th>Conversa</th>
                    </tr>
                </thead>
                <tbody>{pending_rows or '<tr><td colspan="4" class="empty">Nenhuma pendencia aberta para este cliente.</td></tr>'}</tbody>
            </table>
        </section>
        <section class="panel" style="margin-top: 16px;">
            <div class="panel-header"><div class="panel-title">Processos e casos</div></div>
            {matter_form}
            <table>
                <thead>
                    <tr>
                        <th>Caso</th>
                        <th>Numero</th>
                        <th>Status</th>
                        <th>Atualizado em</th>
                    </tr>
                </thead>
                <tbody>{matter_rows or '<tr><td colspan="4" class="empty">Nenhum processo cadastrado.</td></tr>'}</tbody>
            </table>
        </section>
        """
    )
    return _layout("Cliente", "clients", content, current_user)


@crm_router.post("/clientes/{contact_id}")
async def crm_save_client(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    if _is_lawyer(current_user) and not repository.list_conversations_for_contact(contact_id, assigned_user_id=current_user.id):
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a este cliente.")
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body)
    contact_name = form.get("contact_name", [""])[0]
    client_name = form.get("client_name", [""])[0]
    document_number = form.get("document_number", [""])[0]
    client_status = form.get("client_status", ["active"])[0]
    if client_status not in {"active", "inactive"}:
        client_status = "active"
    try:
        repository.save_contact_client_profile(
            organization_id=settings.default_organization_id,
            contact_id=contact_id,
            contact_name=contact_name,
            client_name=client_name,
            document_number=document_number,
            client_status=client_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return RedirectResponse(f"/crm/clientes/{contact_id}", status_code=303)


@crm_router.post("/clientes/{contact_id}/processos")
async def crm_create_client_matter(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    repository = AttendanceRepository(db)
    current_user = _current_user(request)
    if _is_lawyer(current_user) and not repository.list_conversations_for_contact(contact_id, assigned_user_id=current_user.id):
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a este cliente.")
    profile = repository.get_contact_profile(contact_id)
    if not profile or not profile[1]:
        raise HTTPException(status_code=400, detail="Salve a ficha do cliente antes de cadastrar processo.")
    raw_body = (await request.body()).decode("utf-8")
    form = parse_qs(raw_body)
    title = form.get("title", [""])[0].strip()
    if not title:
        raise HTTPException(status_code=400, detail="Nome do processo e obrigatorio.")
    status = form.get("status", ["active"])[0]
    if status not in {"active", "analysis", "documents_pending", "closed"}:
        status = "active"
    repository.create_legal_matter(
        organization_id=settings.default_organization_id,
        client_id=profile[1].id,
        title=title,
        matter_type=form.get("matter_type", [""])[0],
        process_number=form.get("process_number", [""])[0],
        status=status,
    )
    db.commit()
    return RedirectResponse(f"/crm/clientes/{contact_id}", status_code=303)


def _conversation_rows(
    rows: list[tuple[object, object, object | None, int, datetime | None, str | None]],
) -> str:
    html_rows = []
    for conversation, contact, client, message_count, last_message_at, subject in rows:
        name = getattr(client, "display_name", None) or getattr(contact, "display_name", None)
        phone = getattr(contact, "phone_number", None)
        params = urlencode({"q": phone}) if phone else ""
        client_link = f"/crm/clientes/{getattr(contact, 'id')}"
        if params:
            client_link = f"{client_link}?{params}"
        html_rows.append(
            f"""
            <tr>
                <td>
                    <a href="/crm/conversas/{getattr(conversation, 'id')}">#{getattr(conversation, 'id')}</a>
                    <div class="muted"><a href="/crm/conversas/{getattr(conversation, 'id')}">ver conversa</a></div>
                </td>
                <td>
                    <a href="{client_link}">{_h(name)}</a>
                    <div class="muted">{_h(phone)}</div>
                </td>
                <td><div class="subject">{_h(_clip(subject))}</div></td>
                <td>{_status_badge(getattr(conversation, 'status'))}</td>
                <td>{message_count}</td>
                <td>{_dt(last_message_at)}</td>
            </tr>
            """
        )
    return "\n".join(html_rows)


def _pending_row(item: dict, return_to: str = "/crm/pendencias", lawyers: list | None = None) -> str:
    conversation = item["conversation"]
    contact = item["contact"]
    client = item.get("client")
    urgency = _urgency_for_pending(item)
    name = getattr(client, "display_name", None) or getattr(contact, "display_name", None)
    phone = getattr(contact, "phone_number", None)
    created_at = item.get("created_at")
    last_interaction = getattr(conversation, "updated_at", None)
    stale_alert = ""
    if last_interaction and (datetime.now() - last_interaction).days >= 3:
        stale_alert = '<div class="muted">Sem interacao ha mais de 3 dias</div>'
    assigned_user = item.get("assigned_user")
    assigned_text = (
        f'<div class="muted">Responsavel: {escape(assigned_user.full_name)}</div>'
        if assigned_user
        else '<div class="muted">Responsavel: nao definido</div>'
    )
    action_html = f'<a class="button secondary" href="/crm/conversas/{conversation.id}">Ver conversa</a>'
    if item.get("kind") == "handoff" and not assigned_user and lawyers:
        options = "".join(
            f'<option value="{lawyer.id}">{escape(lawyer.full_name)}</option>'
            for lawyer in lawyers
        )
        assign_url = f"/crm/pendencias/handoffs/{item['id']}/atribuir?return_to={escape(return_to)}"
        action_html += f"""
        <form method="post" action="{assign_url}" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <select name="assigned_user_id" required>{options}</select>
            <button type="submit">Atribuir</button>
        </form>
        """
    if item.get("kind") == "handoff" and item.get("can_resolve"):
        resolve_url = f"/crm/pendencias/handoffs/{item['id']}/resolver?return_to={escape(return_to)}"
        action_html += f"""
        <form method="post" action="{resolve_url}" style="display:inline;"
              onsubmit="return confirm('Confirmar que esta pendencia foi resolvida?');">
            <button type="submit">Marcar resolvido</button>
        </form>
        """
    return f"""
    <tr>
        <td>{_urgency_badge(urgency)}</td>
        <td>
            <a href="/crm/clientes/{contact.id}">{_h(name)}</a>
            <div class="muted">{_h(phone)}</div>
        </td>
        <td>
            <div class="subject">{_h(_clip(item.get("reason"), 140))}</div>
            {assigned_text}
            {stale_alert}
        </td>
        <td>{_age_text(created_at)}</td>
        <td>{_dt(last_interaction)}</td>
        <td><div class="toolbar">{action_html}</div></td>
    </tr>
    """
