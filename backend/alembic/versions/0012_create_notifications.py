"""Avisos de cambio significativo entre un analisis y el anterior.

El spec pide alertar cuando la calidad empeora de forma relevante: caida de
mas de 10 puntos, riesgos criticos nuevos, vulnerabilidades introducidas o
cobertura de pruebas que se desploma.

Se guardan en vez de calcularse al vuelo porque un aviso tiene estado propio
(leido o no) y porque describe una transicion concreta entre dos analisis: si
se recalculara, un analisis posterior borraria la historia de lo que paso.

Sin email por ahora: no hay infraestructura de correo y el MVP es gratuito de
principio a fin. El aviso vive dentro de la aplicacion.
"""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            kind VARCHAR(40) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            title VARCHAR(200) NOT NULL,
            body TEXT NOT NULL,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    # La bandeja se consulta siempre por usuario y en orden cronologico
    # inverso; sin este indice cada carga recorreria la tabla entera.
    op.execute(
        "CREATE INDEX idx_notifications_user_created "
        "ON notifications(user_id, created_at DESC);"
    )
    # Un mismo analisis no debe generar dos veces el mismo tipo de aviso, por
    # ejemplo si la tarea se reintenta.
    op.execute(
        "CREATE UNIQUE INDEX idx_notifications_analysis_kind "
        "ON notifications(analysis_id, kind);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE notifications;")
