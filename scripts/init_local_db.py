import sys
import hashlib
import os
import time
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal, engine
from app.core.config import settings
from app.models import Base
from app.models.legal import KnowledgeArticle, Organization, User


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def main() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        inspector = inspect(engine)
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "password_hash" not in user_columns:
            db.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(220)"))
            db.commit()

        conversation_columns = {
            column["name"] for column in inspector.get_columns("conversations")
        }
        if "subject" not in conversation_columns:
            db.execute(text("ALTER TABLE conversations ADD COLUMN subject VARCHAR(220)"))
            db.commit()

        organization = db.scalar(select(Organization).where(Organization.id == 1))
        if not organization:
            db.add(Organization(id=1, name=settings.office_name, status="active"))
            db.flush()

        user = db.scalar(select(User).where(User.email == settings.crm_admin_email))
        if not user:
            db.add(
                User(
                    organization_id=1,
                    full_name="Atendente Humano",
                    email=settings.crm_admin_email,
                    password_hash=hash_password(settings.crm_admin_password),
                    role="attendant",
                    is_active=True,
                )
            )
        elif not user.password_hash:
            user.password_hash = hash_password(settings.crm_admin_password)
        if settings.crm_seed_demo_users:
            for full_name, email in [
                ("Camilla", "camilla@tnadvocacia.local"),
                ("Thiago", "thiago@tnadvocacia.local"),
            ]:
                lawyer = db.scalar(select(User).where(User.email == email))
                if not lawyer:
                    db.add(
                        User(
                            organization_id=1,
                            full_name=full_name,
                            email=email,
                            password_hash=hash_password("123456"),
                            role="lawyer",
                            is_active=True,
                        )
                    )
                elif not lawyer.password_hash:
                    lawyer.password_hash = hash_password("123456")

        article = db.scalar(
            select(KnowledgeArticle).where(
                KnowledgeArticle.organization_id == 1,
                KnowledgeArticle.title == "Regra de encaminhamento humano",
            )
        )
        if not article:
            db.add(
                KnowledgeArticle(
                    organization_id=1,
                    title="Regra de encaminhamento humano",
                    category="seguranca",
                    content=(
                        "Encaminhe para humano quando a mensagem envolver prazo, "
                        "audiencia, processo, documento, valores, honorarios, "
                        "estrategia juridica, urgencia ou insatisfacao."
                    ),
                    is_active=True,
                )
            )

        db.commit()


if __name__ == "__main__":
    last_error: Exception | None = None

    for attempt in range(1, 31):
        try:
            main()
            break
        except OperationalError as exc:
            last_error = exc
            wait_seconds = min(attempt * 2, 15)
            print(
                f"Database is not ready yet "
                f"(attempt {attempt}/30). Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)
    else:
        assert last_error is not None
        raise last_error
