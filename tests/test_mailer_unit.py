"""Unit test de éxito de ``send_mail`` (Mail_Module).

Validates: Requirements 1.5

Req 1.5: WHEN se invoca ``send_mail(subject, body, to)`` y el envío se completa
correctamente, THE Mail_Module SHALL retornar un resultado que indique éxito al
llamador.

Se mockea TODO el transporte HTTP con la librería ``responses`` (sin llamadas de
red reales): se registra el endpoint de token de Entra ID devolviendo 200 con un
``access_token``, y el endpoint ``sendMail`` de Microsoft Graph devolviendo 202.
Se inyecta un ``MailerConfig`` de prueba en ``send_mail(config=...)`` para no
depender del entorno ni del ``.env``.
"""

from __future__ import annotations

import responses

from graph_mailer.config import MailerConfig
from graph_mailer.mailer import send_mail

# Configuración de prueba inyectada: valores ficticios, ningún secreto real.
_TEST_CONFIG = MailerConfig(
    tenant_id="test-tenant-id",
    client_id="test-client-id",
    client_secret="test-client-secret",
    sender_mailbox="phishing@itau.cl",
    test_recipient="qa@example.com",
)

# URLs derivadas de la configuración de prueba (deben coincidir con las que
# construyen token.py y graph.py).
_TOKEN_URL = (
    "https://login.microsoftonline.com/"
    + _TEST_CONFIG.tenant_id
    + "/oauth2/v2.0/token"
)
_GRAPH_URL = (
    "https://graph.microsoft.com/v1.0/users/"
    + _TEST_CONFIG.sender_mailbox
    + "/sendMail"
)

_CORRELATION_ID = "7f1a2b3c-0000-1111-2222-333344445555"


@responses.activate
def test_send_mail_returns_success_on_http_202() -> None:
    """send_mail retorna SendResult(success=True) y status 202 ante un envío OK.

    Validates: Requirements 1.5
    """
    # Token endpoint: 200 con access_token ficticio.
    responses.add(
        responses.POST,
        _TOKEN_URL,
        json={"access_token": "test-access-token", "expires_in": 3600},
        status=200,
    )
    # sendMail endpoint: 202 (aceptado) con correlation id en headers.
    responses.add(
        responses.POST,
        _GRAPH_URL,
        status=202,
        headers={"request-id": _CORRELATION_ID},
    )

    result = send_mail(
        "Prueba de integración Microsoft Graph",
        "Correo de prueba técnica automatizada.",
        "destinatario@example.com",
        config=_TEST_CONFIG,
    )

    assert result.success is True
    assert result.status_code == 202
    assert result.correlation_id == _CORRELATION_ID
    # Se realizaron exactamente dos llamadas: token y sendMail.
    assert len(responses.calls) == 2
