"""Smoke / static checks de contrato y seguridad (Task 9.1).

Validates: Requirements 1.1, 2.2, 3.5, 6.1, 6.2

Estas comprobaciones NO ejercitan el transporte HTTP ni la lógica de envío; son
verificaciones estáticas / de contrato sobre la superficie pública y los
artefactos del proyecto:

- Req 1.1: ``send_mail`` existe y es invocable con la firma ``(subject, body, to)``
  (``config`` como keyword-only opcional).
- Req 2.2: no se importan ``azure-identity`` ni ``msgraph-sdk`` en el código del
  proyecto (paquete ``graph_mailer/`` y ``test_send_email.py``).
- Req 3.5: ``.gitignore`` incluye ``.env`` en la lista de exclusión.
- Req 6.1 / 6.2: ``requirements.txt`` existe con dependencias fijadas (``==``) e
  incluye ``requests`` y ``python-dotenv`` fijados.

La raíz del proyecto se resuelve de forma portable con pathlib para que las
lecturas de ``.gitignore`` y ``requirements.txt`` funcionen en Linux y Windows.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import graph_mailer

# Raíz del proyecto: este archivo vive en <root>/tests/, así que subimos dos
# niveles para obtener <root>.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Req 1.1 — send_mail existe e invocable con firma (subject, body, to)
# ---------------------------------------------------------------------------


def test_send_mail_exists_and_is_callable() -> None:
    """``send_mail`` está exportado por el paquete y es invocable.

    Validates: Requirements 1.1
    """
    assert hasattr(graph_mailer, "send_mail"), "graph_mailer debe exportar send_mail"
    assert callable(graph_mailer.send_mail), "send_mail debe ser invocable"


def test_send_mail_signature_accepts_subject_body_to() -> None:
    """La firma de ``send_mail`` acepta subject, body y to (y config keyword-only).

    Validates: Requirements 1.1
    """
    sig = inspect.signature(graph_mailer.send_mail)
    params = sig.parameters

    # Los tres parámetros posicionales del contrato deben existir.
    for name in ("subject", "body", "to"):
        assert name in params, "send_mail debe aceptar el parámetro %r" % name
        kind = params[name].kind
        assert kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ), "%r debe ser posicional (es %s)" % (name, kind)

    # Debe poder invocarse posicionalmente con (subject, body, to): verificamos
    # que el binding de tres argumentos posicionales es válido.
    bound = sig.bind("asunto", "cuerpo", "destino@example.com")
    assert bound.arguments["subject"] == "asunto"
    assert bound.arguments["body"] == "cuerpo"
    assert bound.arguments["to"] == "destino@example.com"

    # ``config``, si existe, debe ser keyword-only y opcional (tiene default).
    if "config" in params:
        config_param = params["config"]
        assert (
            config_param.kind == inspect.Parameter.KEYWORD_ONLY
        ), "config debe ser keyword-only"
        assert (
            config_param.default is not inspect.Parameter.empty
        ), "config debe ser opcional (tener valor por defecto)"


# ---------------------------------------------------------------------------
# Req 2.2 — No se importan azure-identity ni msgraph-sdk
# ---------------------------------------------------------------------------

# Patrón que detecta líneas de import de los paquetes prohibidos:
#   import azure ...        from azure ... import ...
#   import msgraph ...      from msgraph ... import ...
_FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+(?:azure|msgraph)\b",
    re.MULTILINE,
)


def _project_python_files() -> list[Path]:
    """Archivos .py del proyecto a escanear: graph_mailer/ y test_send_email.py."""
    files = sorted((_PROJECT_ROOT / "graph_mailer").glob("*.py"))
    cli = _PROJECT_ROOT / "test_send_email.py"
    if cli.exists():
        files.append(cli)
    return files


def test_no_azure_or_msgraph_sdk_imports() -> None:
    """Ningún archivo del proyecto importa ``azure-identity`` ni ``msgraph-sdk``.

    Validates: Requirements 2.2
    """
    py_files = _project_python_files()
    # Debe haber al menos los módulos del paquete para que el escaneo sea útil.
    assert py_files, "No se encontraron archivos .py del proyecto para escanear"

    offenders: list[str] = []
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        for match in _FORBIDDEN_IMPORT_RE.finditer(text):
            line = match.group(0).strip()
            offenders.append("%s: %s" % (path.name, line))

    assert not offenders, (
        "No se permiten imports de azure-identity ni msgraph-sdk; "
        "encontrados: " + "; ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Req 3.5 — .gitignore contiene .env
# ---------------------------------------------------------------------------


def test_gitignore_excludes_env_file() -> None:
    """``.gitignore`` existe e incluye ``.env`` como entrada de exclusión.

    Validates: Requirements 3.5
    """
    gitignore = _PROJECT_ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore debe existir en la raíz del proyecto"

    entries = {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert ".env" in entries, ".gitignore debe incluir una entrada exacta '.env'"


# ---------------------------------------------------------------------------
# Req 6.1 / 6.2 — requirements.txt con dependencias fijadas (==)
# ---------------------------------------------------------------------------


def _parse_requirements() -> list[str]:
    """Devuelve las líneas de dependencia (sin comentarios ni vacías)."""
    reqs = _PROJECT_ROOT / "requirements.txt"
    assert reqs.exists(), "requirements.txt debe existir en la raíz del proyecto"
    return [
        line.strip()
        for line in reqs.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_requirements_exist_and_all_pinned() -> None:
    """Cada dependencia en ``requirements.txt`` está fijada con ``==``.

    Validates: Requirements 6.1
    """
    deps = _parse_requirements()
    assert deps, "requirements.txt no debe estar vacío"

    not_pinned = [dep for dep in deps if "==" not in dep]
    assert not not_pinned, (
        "Todas las dependencias deben estar fijadas con '=='; "
        "sin fijar: " + ", ".join(not_pinned)
    )


def test_requirements_include_requests_and_dotenv_pinned() -> None:
    """``requests`` y ``python-dotenv`` están presentes y fijados con ``==``.

    Validates: Requirements 6.2
    """
    deps = _parse_requirements()

    def _is_pinned(package: str) -> bool:
        prefix = package + "=="
        return any(dep.lower().startswith(prefix) for dep in deps)

    assert _is_pinned("requests"), "requirements.txt debe incluir 'requests==' fijado"
    assert _is_pinned(
        "python-dotenv"
    ), "requirements.txt debe incluir 'python-dotenv==' fijado"
