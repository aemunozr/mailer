"""Property-based tests del Token_Client.

Feature: graph-test-email, Property 2: Solicitud de token bien formada

Valida que, para cualquier configuración válida, la solicitud construida por
``fetch_token`` se dirige al endpoint de token del tenant configurado, usa
``grant_type=client_credentials``, incluye
``scope=https://graph.microsoft.com/.default`` y presenta ``client_id`` y
``client_secret`` en el cuerpo de la solicitud.

El transporte HTTP se intercepta con ``responses``: se registra un callback que
captura la ``PreparedRequest`` real emitida por ``requests`` y se aseveran su
método, URL y el cuerpo urlencoded. Así se verifica la FORMA de la solicitud sin
I/O externo.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import responses
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from graph_mailer.config import MailerConfig
from graph_mailer.token import fetch_token

# El ``tenant_id`` se incrusta en el PATH del endpoint; se restringe a un
# segmento de ruta razonable (sin ``/``, ``?``, ``#`` ni espacios) para que la
# URL resultante sea un único segmento comparable de forma determinista.
_tenant_ids = st.text(
    alphabet=st.characters(
        min_codepoint=48,
        max_codepoint=122,
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=40,
)

# ``client_id`` y ``client_secret`` viajan en el cuerpo urlencoded; se admite un
# amplio rango de caracteres imprimibles para ejercitar el encoding con fuerza.
_credential_values = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=64,
)

# El buzón de origen no participa en la solicitud de token, pero MailerConfig lo
# requiere; cualquier texto no vacío sirve.
_mailboxes = st.text(min_size=1, max_size=40)


@st.composite
def _configs(draw) -> MailerConfig:
    """Genera una ``MailerConfig`` válida para la solicitud de token."""
    return MailerConfig(
        tenant_id=draw(_tenant_ids),
        client_id=draw(_credential_values),
        client_secret=draw(_credential_values),
        sender_mailbox=draw(_mailboxes),
        test_recipient="",
    )


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(config=_configs())
def test_token_request_is_well_formed(config: MailerConfig) -> None:
    """Feature: graph-test-email, Property 2: Solicitud de token bien formada.

    Validates: Requirements 2.1
    """
    expected_endpoint = (
        f"https://login.microsoftonline.com/{config.tenant_id}/oauth2/v2.0/token"
    )

    captured: dict[str, object] = {}

    def _capture(request):
        # Captura la PreparedRequest real para aseverar su forma.
        captured["method"] = request.method
        captured["url"] = request.url
        captured["body"] = request.body
        # Respuesta mínima válida para que fetch_token tenga éxito.
        return (200, {}, '{"access_token": "tok", "expires_in": 3600}')

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST,
            expected_endpoint,
            callback=_capture,
            content_type="application/json",
        )

        result = fetch_token(config)

    # fetch_token tuvo éxito y devolvió el token de la respuesta mockeada.
    assert result.access_token == "tok"

    # --- La solicitud se dirige al endpoint del tenant configurado ---
    assert captured["method"] == "POST"
    captured_url = str(captured["url"])
    # Comparamos sin query string: el endpoint (scheme + host + path) debe ser
    # exactamente el del tenant configurado.
    parts = urlsplit(captured_url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == expected_endpoint

    # --- El cuerpo urlencoded contiene los campos requeridos ---
    body = captured["body"]
    body_str = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    # parse_qs decodifica el urlencoding (incluye el '+' y '%XX').
    fields = parse_qs(body_str, keep_blank_values=True)

    assert fields.get("grant_type") == ["client_credentials"]
    assert fields.get("scope") == ["https://graph.microsoft.com/.default"]
    assert fields.get("client_id") == [config.client_id]
    assert fields.get("client_secret") == [config.client_secret]
