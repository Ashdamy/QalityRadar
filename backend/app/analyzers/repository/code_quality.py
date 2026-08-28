"""Calidad del codigo: analizabilidad, modularidad y modificabilidad.

Estas son sub-caracteristicas de mantenibilidad en ISO/IEC 25010. Se miden
leyendo el codigo, nunca ejecutandolo: Python se analiza con el modulo `ast`
de la libreria estandar (que parsea sin evaluar) y JavaScript/TypeScript con
heuristicas de texto, porque no hay parser de JS en el entorno.
"""

import ast
import hashlib
import re
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.structure import IGNORED_DIRECTORIES

PYTHON_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

# Una funcion mas larga que esto suele hacer demasiadas cosas a la vez.
LONG_FUNCTION_LINES = 60
# Por debajo de esta proporcion de comentarios el codigo es dificil de seguir.
LOW_COMMENT_RATIO = 0.03
# Anidamiento por encima del cual el flujo se vuelve dificil de razonar.
DEEP_NESTING = 5

# Se limita el numero de archivos leidos para que un monorepo enorme no
# dispare el tiempo de analisis; la muestra sigue siendo representativa.
MAX_FILES_TO_READ = 1500

_JS_FUNCTION = re.compile(r"\b(function\b|=>|\bclass\b)")
_JS_COMMENT = re.compile(r"^\s*(//|/\*|\*)")
_TS_TYPE_HINT = re.compile(r":\s*(string|number|boolean|void|Promise|[A-Z]\w+)")


class CodeQualityAnalyzer:
    name = "code_quality"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        function_lengths: list[int] = []
        long_functions: list[tuple[str, str, int]] = []
        max_nesting = 0
        deeply_nested: list[tuple[str, int]] = []
        comment_lines = 0
        code_lines = 0
        annotated_functions = 0
        total_functions = 0
        documented_functions = 0
        content_hashes: dict[str, list[str]] = {}
        files_read = 0

        for path in sorted(repo_dir.rglob("*")):
            if files_read >= MAX_FILES_TO_READ:
                break
            if not path.is_file():
                continue
            relative = path.relative_to(repo_dir)
            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                continue
            suffix = path.suffix.lower()
            if suffix not in PYTHON_EXTENSIONS | JS_EXTENSIONS:
                continue

            text = _read(path)
            if not text.strip():
                continue
            files_read += 1
            display = str(relative).replace("\\", "/")

            # Duplicacion exacta: dos archivos con identico contenido.
            digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
            content_hashes.setdefault(digest, []).append(display)

            if suffix in PYTHON_EXTENSIONS:
                stats = _analyse_python(text, display)
            else:
                stats = _analyse_javascript(text, display)

            function_lengths.extend(stats["function_lengths"])
            long_functions.extend(stats["long_functions"])
            comment_lines += stats["comment_lines"]
            code_lines += stats["code_lines"]
            total_functions += stats["total_functions"]
            annotated_functions += stats["annotated_functions"]
            documented_functions += stats["documented_functions"]
            if stats["max_nesting"] > max_nesting:
                max_nesting = stats["max_nesting"]
            if stats["max_nesting"] > DEEP_NESTING:
                deeply_nested.append((display, stats["max_nesting"]))

        duplicated = {h: paths for h, paths in content_hashes.items() if len(paths) > 1}
        duplicated_files = sum(len(paths) - 1 for paths in duplicated.values())

        average_function_lines = (
            round(sum(function_lengths) / len(function_lengths), 1) if function_lengths else 0.0
        )
        comment_ratio = round(comment_lines / code_lines, 4) if code_lines else 0.0
        annotation_ratio = (
            round(annotated_functions / total_functions, 3) if total_functions else 0.0
        )
        documentation_ratio = (
            round(documented_functions / total_functions, 3) if total_functions else 0.0
        )

        metrics = {
            "analyzed_code_files": files_read,
            "total_functions": total_functions,
            "average_function_lines": average_function_lines,
            "long_function_count": len(long_functions),
            "max_nesting_depth": max_nesting,
            "deeply_nested_file_count": len(deeply_nested),
            "comment_ratio": comment_ratio,
            "type_annotation_ratio": annotation_ratio,
            "function_documentation_ratio": documentation_ratio,
            "duplicated_file_count": duplicated_files,
        }

        findings: list[FindingData] = []
        if long_functions:
            worst = max(long_functions, key=lambda item: item[2])
            findings.append(
                FindingData(
                    type="structure",
                    severity="medium" if len(long_functions) > 3 else "low",
                    title=f"Hay {len(long_functions)} funciones demasiado largas",
                    description=(
                        f"La mas larga es `{worst[1]}` con {worst[2]} lineas. Las funciones muy "
                        "extensas concentran varias responsabilidades y son dificiles de probar."
                    ),
                    file_path=worst[0],
                    recommendation="Extrae bloques con sentido propio a funciones mas pequenas.",
                )
            )
        if deeply_nested:
            worst_nest = max(deeply_nested, key=lambda item: item[1])
            findings.append(
                FindingData(
                    type="structure",
                    severity="medium",
                    title="Codigo con anidamiento muy profundo",
                    description=(
                        f"Se alcanzan {worst_nest[1]} niveles de anidamiento. Cada nivel adicional "
                        "multiplica los caminos posibles y dificulta razonar sobre el codigo."
                    ),
                    file_path=worst_nest[0],
                    recommendation="Usa retornos tempranos o extrae la logica interna a funciones.",
                )
            )
        if code_lines > 200 and comment_ratio < LOW_COMMENT_RATIO:
            findings.append(
                FindingData(
                    type="structure",
                    severity="low",
                    title="Codigo con muy pocos comentarios",
                    description=(
                        f"Solo el {comment_ratio:.1%} de las lineas son comentarios. Las decisiones "
                        "no evidentes quedan sin explicar para quien mantenga el codigo."
                    ),
                    recommendation="Documenta el porque de las decisiones no obvias.",
                )
            )
        if duplicated_files:
            ejemplo = next(iter(duplicated.values()))
            findings.append(
                FindingData(
                    type="structure",
                    severity="medium",
                    title=f"Hay {duplicated_files} archivos duplicados",
                    description=(
                        "Se encontraron archivos con contenido identico. Un cambio en uno se olvida "
                        "facilmente en el otro, y las correcciones se aplican a medias."
                    ),
                    file_path=ejemplo[0],
                    recommendation="Extrae el contenido comun a un unico modulo compartido.",
                )
            )

        return AnalyzerResult(dimension="maintainability", metrics=metrics, findings=findings)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _analyse_python(text: str, display: str) -> dict:
    stats = _empty_stats()
    lines = text.splitlines()
    stats["comment_lines"] = sum(1 for line in lines if line.strip().startswith("#"))
    stats["code_lines"] = sum(1 for line in lines if line.strip())

    try:
        tree = ast.parse(text)  # parsea sin ejecutar nada
    except SyntaxError:
        return stats

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stats["total_functions"] += 1
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            stats["function_lengths"].append(length)
            if length > LONG_FUNCTION_LINES:
                stats["long_functions"].append((display, node.name, length))
            if node.returns is not None or any(a.annotation for a in node.args.args):
                stats["annotated_functions"] += 1
            if ast.get_docstring(node):
                stats["documented_functions"] += 1

    stats["max_nesting"] = _python_nesting(tree)
    return stats


def _python_nesting(tree: ast.AST) -> int:
    nesting_nodes = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)

    def depth(node: ast.AST, current: int = 0) -> int:
        deepest = current
        for child in ast.iter_child_nodes(node):
            child_depth = current + 1 if isinstance(child, nesting_nodes) else current
            deepest = max(deepest, depth(child, child_depth))
        return deepest

    return depth(tree)


def _analyse_javascript(text: str, display: str) -> dict:
    """Heuristica de texto: no hay parser de JS disponible en el entorno."""
    stats = _empty_stats()
    lines = text.splitlines()
    stats["comment_lines"] = sum(1 for line in lines if _JS_COMMENT.match(line))
    stats["code_lines"] = sum(1 for line in lines if line.strip())
    stats["total_functions"] = sum(1 for line in lines if _JS_FUNCTION.search(line))
    stats["annotated_functions"] = sum(1 for line in lines if _TS_TYPE_HINT.search(line))
    # Se acota para que la proporcion nunca supere 1 pese a ser una heuristica.
    stats["annotated_functions"] = min(stats["annotated_functions"], stats["total_functions"])

    depth = 0
    max_depth = 0
    for line in lines:
        stripped = line.strip()
        if _JS_COMMENT.match(stripped):
            continue
        depth += stripped.count("{") - stripped.count("}")
        max_depth = max(max_depth, depth)
    stats["max_nesting"] = max(0, max_depth)
    return stats


def _empty_stats() -> dict:
    return {
        "function_lengths": [],
        "long_functions": [],
        "comment_lines": 0,
        "code_lines": 0,
        "total_functions": 0,
        "annotated_functions": 0,
        "documented_functions": 0,
        "max_nesting": 0,
    }
