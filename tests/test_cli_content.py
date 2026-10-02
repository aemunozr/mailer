"""Tests de contenido anti-phishing del Test_CLI (``test_send_email.py``).

Validates: Requirements 5.1, 5.2, 5.3

El contenido del correo de prueba debe ser inequívocamente identificable como una
validación técnica automatizada y NO debe contener elementos de phishing.

Para inspeccionar el asunto y el cuerpo que el CLI realmente envía, se mockea
``send_mail`` para registrar sus argumentos (subject/body) y se invoca
``cli.main()`` con la configuración inyectada vía ``monkeypatch`` de
``load_config``. Las aserciones se hacen sobre los valores capturados.

Requisitos cubiertos:
- 5.1: el asunto identifica el mensaje como prueba de integración técnica
  ("Prueba de integración Microsoft Graph").
- 5.2: el cuerpo indica explícitamente que es una validación automatizada.
- 5.3: el contenido no contiene elementos de phishing (sin enlaces http/https,
  sin solicitud de credenciales/contraseñas, sin urgencia artificial).
"""

from __future__ import annotations

import importlib
import re

from graph_mailer.config import MailerConfig
from graph_mailer.mailer import SendResult

# El Test_CLI vive en la raíz del proyecto como ``test_send_email.py``.
cli = importlib.import_module("test_send_email")

_TEST_CONFIG = MailerConfig(
    tenant_id="test-tenant-id",
    client_id="test-client-id",
    client_secret="test-client-secret",
    sender_mailbox="phishing@itau.cl",
    test_recipient="qa@example.com",
)

# Términos típicos de solicitud de credenciales / phishing (chequeo case-insensitive).
_CREDENTIAL_TERMS = (
    "contraseña",
    "contrasena",
    "password",
    "clave",
    "usuario y contraseña",
    "credencial",
    "credenciales",
    "pin",
    "cuenta bloqueada",
    "verifique su cuenta",
    "verificar su cuenta",
    "inicie sesión",
    "inicie sesion",
    "haga clic",
    "haz clic",
    "click aquí",
    "click aqui",
)

# Términos de urgencia artificial típicos de phishing.
_URGENCY_TERMS = (
    "urgente",
    "inmediato",
    "inmediatamente",
    "de inmediato",
    "ahora mismo",
    "expira",
    "vencimiento",
    "antes de que",
    "última oportunidad",
    "ultima oportunidad",
    "acción requerida",
    "accion requerida",
    "suspendida",
    "suspendido",
)


def _capture_subject_body(monkeypatch) -> dict:
    """Invoca el CLI con send_mail mockeado y devuelve el subject/body enviados."""
    monkeypatch.setattr(cli, "load_config", lambda: _TEST_CONFIG)

    captured: dict[str, str] = {}

    def _fake_send_mail(subject, body, to, *, config=None):
        captured["subject"] = subject
        captured["body"] = body
        captured["to"] = to
        return SendResult(
            success=True,
            status_code=202,
            correlation_id="corr-content-123",
            message="OK",
        )

    monkeypatch.setattr(cli, "send_mail", _fake_send_mail)

    cli.main()
    return captured


def test_subject_identifies_technical_integration(monkeypatch) -> None:
    """El asunto identifica el mensaje como prueba de integración técnica.

    Validates: Requirements 5.1
    """
    captured = _capture_subject_body(monkeypatch)
    assert captured["subject"] == "Prueba de integración Microsoft Graph"


def test_body_declares_automated_validation(monkeypatch) -> None:
    """El cuerpo indica explícitamente que es una validación automatizada.

    Validates: Requirements 5.2
    """
    captured = _capture_subject_body(monkeypatch)
    body_lower = captured["body"].lower()

    # Debe declarar que es una prueba técnica automatizada de integración.
    assert "prueba" in body_lower
    assert "automática" in body_lower or "automatizada" in body_lower
    assert "integración" in body_lower or "integracion" in body_lower


def test_content_has_no_phishing_elements(monkeypatch) -> None:
    """El contenido no contiene elementos de phishing (enlaces, credenciales, urgencia).

    Validates: Requirements 5.3
    """
    captured = _capture_subject_body(monkeypatch)
    content = (captured["subject"] + "\n" + captured["body"]).lower()

    # --- Sin enlaces http/https ---
    assert not re.search(r"https?://", content), (
        "El contenido no debe incluir enlaces http/https."
    )

    # --- Sin solicitud de credenciales/contraseñas ---
    for term in _CREDENTIAL_TERMS:
        assert term not in content, (
            f"El contenido no debe solicitar credenciales (término: {term!r})."
        )

    # --- Sin urgencia artificial ---
    for term in _URGENCY_TERMS:
        assert term not in content, (
            f"El contenido no debe inducir urgencia artificial (término: {term!r})."
        )
