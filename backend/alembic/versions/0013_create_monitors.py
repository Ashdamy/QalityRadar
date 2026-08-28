"""Proyectos enganchados: se reanalizan solos cuando cambian.

La idea es que el usuario no tenga que acordarse de pulsar "Analizar". Deja un
repositorio (o una direccion) vigilado y ve como evoluciona su calidad segun
va trabajando.

`last_commit_sha` es lo que hace viable la funcion. Analizar cada X minutos
seria carisimo y casi siempre inutil, porque entre dos comprobaciones lo normal
es que no se haya subido nada. En vez de eso se guarda el ultimo commit visto:
preguntarle a GitHub cual es el actual cuesta una llamada y no clona nada, y
solo cuando difiere se lanza el analisis completo.

Para direcciones no hay commit, asi que se usa `last_fingerprint`, donde se
guarda el ETag o el Last-Modified que devuelve el servidor. Sirve para lo
mismo: saber si la pagina cambio sin descargarla entera.
"""

from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE monitors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repository_id UUID REFERENCES repositories(id) ON DELETE CASCADE,
            app_id UUID REFERENCES deployed_apps(id) ON DELETE CASCADE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            check_interval_minutes INTEGER NOT NULL DEFAULT 60,
            last_commit_sha VARCHAR(40),
            last_fingerprint VARCHAR(255),
            last_checked_at TIMESTAMPTZ,
            last_triggered_at TIMESTAMPTZ,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT monitors_target_chk CHECK (
                (repository_id IS NOT NULL AND app_id IS NULL) OR
                (repository_id IS NULL AND app_id IS NOT NULL)
            )
        );
    """)
    # Un mismo objetivo no puede vigilarse dos veces: serian analisis
    # duplicados y avisos por partida doble.
    op.execute(
        "CREATE UNIQUE INDEX idx_monitors_repository ON monitors(repository_id) "
        "WHERE repository_id IS NOT NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_monitors_app ON monitors(app_id) "
        "WHERE app_id IS NOT NULL;"
    )
    # El planificador recorre los activos ordenados por cuando les toca.
    op.execute(
        "CREATE INDEX idx_monitors_due ON monitors(is_active, last_checked_at) "
        "WHERE is_active;"
    )


def downgrade() -> None:
    op.execute("DROP TABLE monitors;")
