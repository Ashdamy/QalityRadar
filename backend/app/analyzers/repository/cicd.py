"""CI/CD: automatizacion de la integracion y el despliegue.

Aporta a portabilidad (instalabilidad reproducible) y es senal indirecta de
fiabilidad: un proyecto que ejecuta sus pruebas en cada cambio detecta las
regresiones antes de que lleguen a produccion.

Se leen los ficheros de configuracion; nunca se ejecutan.
"""

from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData

# Rutas donde vive la configuracion de los sistemas de CI mas usados.
CI_LOCATIONS = {
    "GitHub Actions": (".github/workflows",),
    "GitLab CI": (".gitlab-ci.yml",),
    "CircleCI": (".circleci/config.yml",),
    "Travis CI": (".travis.yml",),
    "Jenkins": ("Jenkinsfile",),
    "Azure Pipelines": ("azure-pipelines.yml",),
    "Drone": (".drone.yml",),
    "Bitbucket Pipelines": ("bitbucket-pipelines.yml",),
}

# Indicios de que el pipeline ejecuta pruebas y no solo compila o despliega.
TEST_KEYWORDS = ("pytest", "npm test", "yarn test", "go test", "cargo test", "jest", "vitest",
                 "rspec", "phpunit", "mvn test", "gradle test", "tox", "unittest")
LINT_KEYWORDS = ("lint", "eslint", "ruff", "flake8", "rubocop", "golangci", "prettier", "black")
DEPLOY_KEYWORDS = ("deploy", "publish", "release", "docker push", "vercel", "netlify",
                   "kubectl", "helm", "terraform apply")


class CicdAnalyzer:
    name = "cicd"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        detected: list[str] = []
        config_texts: list[str] = []

        for system, locations in CI_LOCATIONS.items():
            for location in locations:
                target = repo_dir / location
                if target.is_dir():
                    archivos = [p for p in target.rglob("*") if p.suffix.lower() in {".yml", ".yaml"}]
                    if archivos:
                        detected.append(system)
                        config_texts.extend(_read(p) for p in archivos)
                elif target.is_file():
                    detected.append(system)
                    config_texts.append(_read(target))

        blob = "\n".join(config_texts).lower()
        runs_tests = any(k in blob for k in TEST_KEYWORDS)
        runs_lint = any(k in blob for k in LINT_KEYWORDS)
        has_deploy = any(k in blob for k in DEPLOY_KEYWORDS)

        metrics = {
            "has_ci": bool(detected),
            "ci_systems": sorted(set(detected)),
            "ci_config_file_count": len(config_texts),
            "ci_runs_tests": runs_tests,
            "ci_runs_lint": runs_lint,
            "ci_has_deploy_stage": has_deploy,
        }

        findings: list[FindingData] = []
        if not detected:
            findings.append(
                FindingData(
                    type="cicd",
                    severity="medium",
                    title="No hay integracion continua configurada",
                    description=(
                        "No se encontro configuracion de CI. Nada comprueba automaticamente los "
                        "cambios antes de que se integren, asi que una regresion solo se detecta "
                        "cuando alguien la sufre."
                    ),
                    recommendation="Anade un flujo de CI que al menos ejecute las pruebas en cada cambio.",
                )
            )
        elif not runs_tests:
            findings.append(
                FindingData(
                    type="cicd",
                    severity="medium",
                    title="La integracion continua no ejecuta pruebas",
                    description=(
                        f"Se detecto {', '.join(sorted(set(detected)))}, pero su configuracion no "
                        "parece ejecutar la bateria de pruebas. Un pipeline que no prueba no "
                        "protege de regresiones."
                    ),
                    recommendation="Anade un paso que ejecute las pruebas en cada cambio.",
                )
            )

        return AnalyzerResult(dimension="portability", metrics=metrics, findings=findings)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
