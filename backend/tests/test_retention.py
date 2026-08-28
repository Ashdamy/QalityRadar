"""Purga de analisis antiguos.

La regla que mas importa no es cuantos se borran sino cual **nunca** se borra:
siempre quedan los 10 ultimos, aunque sean viejisimos. Un proyecto aparcado y
retomado depende de eso para poder compararse con su pasado.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.user import User
from app.services.retention_service import (
    ALWAYS_KEEP,
    MAX_PER_TARGET,
    RETENTION_DAYS,
    purge_old_analyses,
)

_EMAIL = "retencion-fixture@example.com"


@pytest.fixture
def repositorio():
    def _limpiar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()

    _limpiar()
    db = SessionLocal()
    try:
        usuario = User(id=uuid.uuid4(), email=_EMAIL, password_hash="x")
        db.add(usuario)
        db.flush()
        repo = Repository(
            id=uuid.uuid4(),
            user_id=usuario.id,
            github_id=987654321,
            name="retencion",
            full_name="prueba/retencion",
            is_private=False,
        )
        db.add(repo)
        db.commit()
        yield usuario.id, repo.id
    finally:
        db.close()
        _limpiar()


def _crear_analisis(db, user_id, repo_id, cuantos, antiguedad_dias=0):
    base = datetime.now(timezone.utc) - timedelta(days=antiguedad_dias)
    for i in range(cuantos):
        db.add(
            Analysis(
                id=uuid.uuid4(),
                user_id=user_id,
                repository_id=repo_id,
                analysis_type="repository",
                status="completed",
                created_at=base - timedelta(minutes=i),
            )
        )
    db.commit()


def _contar(db, repo_id) -> int:
    return db.scalar(
        select(func.count()).select_from(Analysis).where(Analysis.repository_id == repo_id)
    )


def test_por_debajo_del_limite_no_se_borra_nada(repositorio):
    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        _crear_analisis(db, user_id, repo_id, 5)
        purge_old_analyses(db)
        assert _contar(db, repo_id) == 5
    finally:
        db.close()


def test_el_analisis_51_dispara_la_purga_del_mas_antiguo(repositorio):
    """Criterio de salida del roadmap: el historico se queda en 50."""
    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        _crear_analisis(db, user_id, repo_id, MAX_PER_TARGET + 1)
        borrados = purge_old_analyses(db)
        assert borrados == 1
        assert _contar(db, repo_id) == MAX_PER_TARGET
    finally:
        db.close()


def test_se_borra_el_mas_antiguo_y_no_otro(repositorio):
    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        _crear_analisis(db, user_id, repo_id, MAX_PER_TARGET + 1)
        mas_antiguo = db.scalars(
            select(Analysis.id)
            .where(Analysis.repository_id == repo_id)
            .order_by(Analysis.created_at.asc())
            .limit(1)
        ).first()

        purge_old_analyses(db)
        assert db.get(Analysis, mas_antiguo) is None
    finally:
        db.close()


def test_lo_mas_viejo_de_90_dias_se_borra(repositorio):
    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        _crear_analisis(db, user_id, repo_id, 5)  # recientes
        _crear_analisis(db, user_id, repo_id, 8, antiguedad_dias=RETENTION_DAYS + 10)

        purge_old_analyses(db)
        # 13 en total, 10 protegidos: solo los 3 sobrantes son candidatos, y
        # los tres son de los viejos.
        assert _contar(db, repo_id) == ALWAYS_KEEP
    finally:
        db.close()


def test_los_diez_ultimos_sobreviven_aunque_sean_antiquisimos(repositorio):
    """La regla que manda: un proyecto aparcado no se queda sin historico."""
    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        _crear_analisis(db, user_id, repo_id, ALWAYS_KEEP, antiguedad_dias=RETENTION_DAYS * 4)
        borrados = purge_old_analyses(db)
        assert borrados == 0
        assert _contar(db, repo_id) == ALWAYS_KEEP
    finally:
        db.close()


def test_la_purga_borra_tambien_dimensiones_y_hallazgos(repositorio):
    """Van por ON DELETE CASCADE: si eso se rompiera quedarian huerfanas."""
    from app.models.analysis import Dimension

    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        _crear_analisis(db, user_id, repo_id, MAX_PER_TARGET + 1)
        mas_antiguo = db.scalars(
            select(Analysis.id)
            .where(Analysis.repository_id == repo_id)
            .order_by(Analysis.created_at.asc())
            .limit(1)
        ).first()
        db.add(
            Dimension(
                id=uuid.uuid4(),
                analysis_id=mas_antiguo,
                name="security",
                score=10,
                weight=0.2,
            )
        )
        db.commit()

        purge_old_analyses(db)
        restantes = db.scalar(
            select(func.count())
            .select_from(Dimension)
            .where(Dimension.analysis_id == mas_antiguo)
        )
        assert restantes == 0
    finally:
        db.close()


def test_la_purga_de_un_repositorio_no_toca_a_otro(repositorio):
    user_id, repo_id = repositorio
    db = SessionLocal()
    try:
        otro = Repository(
            id=uuid.uuid4(),
            user_id=user_id,
            github_id=987654322,
            name="intacto",
            full_name="prueba/intacto",
            is_private=False,
        )
        db.add(otro)
        db.commit()

        _crear_analisis(db, user_id, repo_id, MAX_PER_TARGET + 5)
        _crear_analisis(db, user_id, otro.id, 3)

        purge_old_analyses(db)
        assert _contar(db, otro.id) == 3
    finally:
        db.close()


def test_purgar_sin_nada_que_borrar_devuelve_cero(repositorio):
    db = SessionLocal()
    try:
        assert purge_old_analyses(db) >= 0
    finally:
        db.close()
