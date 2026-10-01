"""Property-based tests del Graph_Client.

Feature: graph-test-email, Property 1: Solicitud sendMail bien formada

Valida que, para cualquier subject/body/to válidos, la solicitud construida por
``send_via_graph`` usa ``POST`` contra
``/v1.0/users/{sender_mailbox}/sendMail`` (con el ``sender_mailbox`` en la
ruta), incluye el header ``Authorization: Bearer {access_token}`` y produce un
payload sin ``ccRecipients``, ``bccRecipients`` ni ``attachments`` y con un
único ``toRecipients``.

El transporte HTTP se intercepta con ``responses``: se registra un callback que
captura la ``PreparedRequest`` real (método, URL, headers, cuerpo JSON) y se
aseveran. Así se verifica la FORMA de la solicitud sin I/O externo.
"""

from __future__ import annotations

import json

import responses
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from graph_mailer.graph import send_via_graph

# El ``sender_mailbox`` se incrusta en el PATH del endpoint; se restringe a
# caracteres de buzón razonables (sin ``/``, ``?``, ``#`` ni espacios) para que
# la URL resultante sea determinista y comparable.
_mailboxes = st.text(
    alphabet=st.characters(
        min_codepoint=48,
        max_codepoint=122,
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_.@",
    ),
    min_size=1,
    max_size=40,
)

# subject/body/to admiten un amplio rango de texto imprimible (viajan en JSON).
_text_values = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=80,
)
_to_values = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=80,
)

# El token es un Secret_Value cualquiera no vacío; se usa para el header Bearer.
_tokens = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=64,
)


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    access_token=_tokens,
    sender_mailbox=_mailboxes,
    subject=_text_values,
    body=_text_values,
    to=_to_values,
)
def test_sendmail_request_is_well_formed(
    access_token: str,
    sender_mailbox: str,
    subject: str,
    body: str,
    to: str,
) -> None:
    """Feature: graph-test-email, Property 1: Solicitud sendMail bien formada.

    Validates: Requirements 1.2, 1.3, 1.4, 2.3
    """
    expected_url = (
        f"https://graph.microsoft.com/v1.0/users/{sender_mailbox}/sendMail"
    )

    captured: dict[str, object] = {}

    def _capture(request):
        captured["method"] = request.method
        captured["url"] = request.url
        captured["headers"] = request.headers
        captured["body"] = request.body
        # 202 Accepted con un correlation id, como responde Graph en éxito.
        return (202, {"request-id": "corr-123"}, "")

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST,
            expected_url,
            callback=_capture,
        )

        send_via_graph(access_token, sender_mailbox, subject, body, to)

    # --- Método POST contra la URL con el sender en el path ---
    assert captured["method"] == "POST"
    assert str(captured["url"]) == expected_url
    # El sender_mailbox aparece en el segmento de ruta esperado.
    assert f"/users/{sender_mailbox}/sendMail" in str(captured["url"])

    # --- Header Authorization: Bearer <token> ---
    headers = captured["headers"]
    assert headers.get("Authorization") == f"Bearer {access_token}"

    # --- Payload sin cc/bcc/adjuntos y con un único toRecipients ---
    raw_body = captured["body"]
    body_str = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body)
    payload = json.loads(body_str)

    message = payload["message"]
    assert "ccRecipients" not in message
    assert "bccRecipients" not in message
    assert "attachments" not in message

    recipients = message["toRecipients"]
    assert len(recipients) == 1
    assert recipients[0]["emailAddress"]["address"] == to
