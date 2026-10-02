"""Unit tests de diagnóstico del Test_CLI (``test_send_email.py``).

Validates: Requirements 4.1, 4.2, 4.4, 4.5

El Test_CLI es un script ejecutable con ``main() -> int`` (NO un test de
pytest). Aquí se importa como módulo con ``importlib`` y se invoca ``cli.main()``
con el transporte/``send_mail`` mockeado para ejercer cada ruta de diagnóstico.

Para controlar la ejecución sin red ni ``.env`` real, se parchean los símbolos
que el CLI importó a nivel de módulo (``load_config`` y ``send_mail``) mediante
``monkeypatch``. La salida se captura con ``capsys``.

Requisitos cubiertos:
- 4.1: el CLI lee la configuración vía ``load_config`` e invoca ``send_mail`` UNA vez.
- 4.2: en éxito, el CLI muestra diagnóstico que confirma la obtención del token.
- 4.4: ante HTTP 401, el CLI muestra un mensaje de falla de autenticación.
- 4.5: ante HTTP 403, el CLI muestra un mensaje de falta de permisos.
"""

from __future__ import annotations

import importlib

from graph_mailer.config import MailerConfig
from graph_mailer.mailer import SendResult

# El Test_CLI vive en la raíz del proyecto como ``test_send_email.py``.
cli = importlib.import_module("test_send_email")

# Configuración de prueba inyectada: valores ficticios, ningún secreto real.
_TEST_CONFIG = MailerConfig(
    tenant_id="test-tenant-id",
    client_id="test-client-id",
    client_secret="test-client-secret",
    sender_mailbox="phishing@itau.cl",
    test_recipient="qa@example.com",
)


def _patch_config(monkeypatch) -> None:
    """Hace que ``load_config`` del CLI devuelva la configuración de prueba."""
    monkeypatch.setattr(cli, "load_config", lambda: _TEST_CONFIG)


def test_cli_reads_config_and_invokes_send_mail_once(monkeypatch, capsys) -> None:
    """El CLI lee la config e invoca send_mail exactamente una vez.

    Validates: Requirements 4.1
    """
    _patch_config(monkeypatch)

    calls: list[dict] = []

    def _fake_send_mail(subject, body, to, *, config=None):
        calls.append(
            {"subject": subject, "body": body, "to": to, "config": config}
        )
        return SendResult(
            success=True,
            status_code=202,
            correlation_id="corr-abc-123",
            message="OK",
        )

    monkeypatch.setattr(cli, "send_mail", _fake_send_mail)

    exit_code = cli.main()

    # send_mail se invocó EXACTAMENTE una vez.
    assert len(calls) == 1
    # El destinatario proviene de config.test_recipient (Config_Loader).
    assert calls[0]["to"] == _TEST_CONFIG.test_recipient
    # Se le pasó la configuración leída por el CLI.
    assert calls[0]["config"] is _TEST_CONFIG
    # Éxito -> código de salida 0.
    assert exit_code == 0

    out = capsys.readouterr().out
    # Confirmación de que se cargó la configuración.
    assert "Cargando configuración" in out


def test_cli_shows_token_obtained_on_success(monkeypatch, capsys) -> None:
    """En éxito, el CLI confirma la obtención del token (sin exponer su valor).

    Validates: Requirements 4.2
    """
    _patch_config(monkeypatch)

    monkeypatch.setattr(
        cli,
        "send_mail",
        lambda subject, body, to, *, config=None: SendResult(
            success=True,
            status_code=202,
            correlation_id="corr-abc-123",
            message="OK",
        ),
    )

    exit_code = cli.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    # Diagnóstico de token obtenido.
    assert "token obtenido" in out.lower()


def test_cli_shows_auth_failure_on_401(monkeypatch, capsys) -> None:
    """Ante HTTP 401, el CLI muestra un mensaje de falla de autenticación.

    Validates: Requirements 4.4
    """
    _patch_config(monkeypatch)

    monkeypatch.setattr(
        cli,
        "send_mail",
        lambda subject, body, to, *, config=None: SendResult(
            success=False,
            status_code=401,
            correlation_id="corr-401",
            message="El envío vía Microsoft Graph no fue aceptado (HTTP 401).",
        ),
    )

    exit_code = cli.main()
    out = capsys.readouterr().out

    # Fallo -> código de salida distinto de 0.
    assert exit_code != 0
    # El status HTTP 401 aparece en la salida.
    assert "401" in out
    # Mensaje legible de falla de autenticación.
    assert "autenticación" in out.lower()


def test_cli_shows_permission_failure_on_403(monkeypatch, capsys) -> None:
    """Ante HTTP 403, el CLI muestra un mensaje de falta de permisos.

    Validates: Requirements 4.5
    """
    _patch_config(monkeypatch)

    monkeypatch.setattr(
        cli,
        "send_mail",
        lambda subject, body, to, *, config=None: SendResult(
            success=False,
            status_code=403,
            correlation_id="corr-403",
            message="El envío vía Microsoft Graph no fue aceptado (HTTP 403).",
        ),
    )

    exit_code = cli.main()
    out = capsys.readouterr().out

    assert exit_code != 0
    # El status HTTP 403 aparece en la salida.
    assert "403" in out
    # Mensaje legible de falta de permisos.
    assert "permisos" in out.lower()
