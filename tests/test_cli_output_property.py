"""Property test de status HTTP y Correlation_Id en la salida del Test_CLI.

Feature: graph-test-email, Property 7: El CLI muestra status HTTP y Correlation_Id

Validates: Requirements 4.3

Property 7 (design.md): para cualquier respuesta de ``sendMail`` con un status
HTTP y un ``Correlation_Id`` dados, la salida del ``Test_CLI`` incluye tanto ese
código de estado HTTP como ese ``Correlation_Id``.

Estrategia: el Test_CLI (``test_send_email.py``) se importa como módulo con
``importlib``. Se parchean los símbolos que importó (``load_config`` y
``send_mail``) con ``monkeypatch`` para no depender del entorno ni de la red: por
cada ejemplo, ``send_mail`` devuelve un ``SendResult`` con el status y el
correlation id generados. Se captura stdout con ``capsys`` y se asevera que
AMBOS valores aparecen en la salida.
"""

from __future__ import annotations

import importlib

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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

# Status HTTP 2xx y 4xx que puede devolver sendMail (y rutas de diagnóstico).
_status_codes = st.sampled_from([200, 201, 202, 204, 400, 401, 403, 404, 429])

# Correlation ids con forma plausible (GUID-like y variantes), siempre no vacíos
# y sin espacios para que la comparación de subcadena en stdout sea significativa.
_correlation_ids = st.text(
    alphabet=st.characters(
        min_codepoint=48,
        max_codepoint=122,
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=40,
)


@settings(
    max_examples=150,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(status_code=_status_codes, correlation_id=_correlation_ids)
def test_cli_output_includes_status_and_correlation_id(
    status_code: int,
    correlation_id: str,
    monkeypatch,
    capsys,
) -> None:
    """Feature: graph-test-email, Property 7: El CLI muestra status HTTP y Correlation_Id.

    Validates: Requirements 4.3
    """
    monkeypatch.setattr(cli, "load_config", lambda: _TEST_CONFIG)

    monkeypatch.setattr(
        cli,
        "send_mail",
        lambda subject, body, to, *, config=None: SendResult(
            success=(status_code == 202),
            status_code=status_code,
            correlation_id=correlation_id,
            message="diagnóstico seguro",
        ),
    )

    cli.main()
    out = capsys.readouterr().out

    # El status HTTP aparece en la salida.
    assert str(status_code) in out, (
        f"El status HTTP {status_code} no aparece en la salida del CLI."
    )
    # El Correlation_Id aparece en la salida.
    assert correlation_id in out, (
        f"El Correlation_Id {correlation_id!r} no aparece en la salida del CLI."
    )
