"""
Veritabanı bağlantısı ve oturum yönetimi.

SQLAlchemy engine, session factory ve FastAPI Dependency Injection
ile kullanılacak get_db generator fonksiyonu burada tanımlanır.
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Ortam değişkeni ile yapılandırılabilir (Render, Railway vb.)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mola_sistemi.db")

_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
)

# Oturum fabrikası: her istek için bağımsız bir Session üretir
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Tüm ORM modellerinin miras alacağı temel sınıf."""

    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI Dependency Injection ile kullanılan veritabanı oturumu.

    Her HTTP isteği için yeni bir oturum açılır; istek tamamlandığında
    oturum güvenli şekilde kapatılır (commit/rollback işlemi route katmanında yapılır).

    Kullanım:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Uygulama başlangıcında tüm tabloları oluşturur ve şema güncellemelerini uygular."""
    from sqlalchemy import text

    # Döngüsel import'u önlemek için modeller burada import edilir
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Mevcut SQLite veritabanına yeni sütunlar ekleme (idempotent)
    migrations = [
        "ALTER TABLE breaks ADD COLUMN planned_duration_minutes INTEGER NOT NULL DEFAULT 15",
        "ALTER TABLE employees ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'personel'",
        "ALTER TABLE employees ADD COLUMN password_hash VARCHAR(128) NOT NULL DEFAULT ''",
        "ALTER TABLE employees ADD COLUMN is_on_break BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE employees ADD COLUMN break_start_time DATETIME",
        "ALTER TABLE employees ADD COLUMN break_duration_minutes INTEGER",
        "ALTER TABLE employees ADD COLUMN assigned_by VARCHAR(150)",
        "ALTER TABLE employees ADD COLUMN kullanilan_mola INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE employees ADD COLUMN mola_kota_tarihi DATE",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # Sütun zaten mevcut

    # Sabit admin hesabını garanti altına al
    db = SessionLocal()
    try:
        from app import crud

        crud.ensure_admin_user(db)
    finally:
        db.close()
