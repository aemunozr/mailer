"""Property test de no exposición de secretos en el Mail_Module.

Feature: graph-test-email, Property 5: Ningún secreto aparece en la salida ni en
los errores del módulo

Validates: Requirements 2.4, 3.2

Property 5 (design.md): Para cualquier conjunto de ``Secret_Value`` (TENANT_ID,
CLIENT_ID, CLIENT_SECRET, Access_Token) y para cualquier resultado de las
llamadas HTTP (éxito o fallo), ningún ``Secret_Value`` SHALL aparecer en los
logs, en la salida ni en los mensajes de error emitidos por el ``Mail_Module``.

Estrategia: se mockea TODO el transporte HTTP con ``responses`` (sin red real).
Para cada ejemplo se generan secretos aleatorios distintivos (tenant/client/
secret/access_token) y se ejerce ``send_mail`` en tres rutas:

    - éxito  : token 200 + sendMail 202      -> SendResult(success=True)
    - graph  : token 200 + sendMail 403      -> SendResult(success=False)
    - token  : token 401                      -> TokenError

En cada ruta se capturan todas las superficies observables del módulo (repr y
``message`` del ``SendResult``; ``str`` de la excepción; registros de logging vía
``caplog``) y se asevera que NINGÚN ``Secret_Value`` aparece en ellas.
"""

from __future__ import annotations

import logging

import responses
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from graph_mailer.config import MailerConfig
from graph_mailer.errors import TokenError
from graph_mailer.mailer import send_mail

# Marcador antepuesto a cada valor secreto. Contiene ``::`` y minúsculas, que no
# aparecen en texto fijo de diagnóstico, nombres de variables (MAYÚSCULAS) ni en
# el buzón/destinatario de prueba. Hace la búsqueda de subcadena significativa y
# libre de colisiones incidentales (evita falsos positivos).
_SECRET_MARKER = "secret::"

# Cuerpos de valores secretos: texto imprimible sin comillas problemáticas; el
# marcador garantiza unicidad respecto del resto de la salida.
_secret_bodies = st.text(
    alphabet=st.characters(
        min_codepoint=33,
        max_codepoint=126,
        blacklist_characters="\"'\\",
    ),
    min_size=1,
    max_size=40,
)
_secret_values = _secret_bodies.map(lambda body: _SECRET_MARKER + body)

# Rutas de ejecución a ejercer (status del token y de sendMail por ruta).
_SUCCESS = "success"  # token 200 -> sendMail 202
_GRAPH_FORBIDDEN = "graph_403"  # token 200 -> sendMail 403
_TOKEN_FAILURE = "token_401"  # token 401 -> TokenError
_routes = st.sampled_from([_SUCCESS, _GRAPH_FORBIDDEN, _TOKEN_FAILURE])


def _token_url(tenant_id: str) -> str:
    return (
        "https://login.microsoftonline.com/"
        + tenant_id
        + "/oauth2/v2.0/token"
    )


def _graph_url(sender_mailbox: str) -> str:
    return (
        "https://graph.microsoft.com/v1.0/users/"
        + sender_mailbox
        + "/sendMail"
    )


def _collect_secret_surfaces(config: MailerConfig, access_token: str, route: str):
    """Ejerce ``send_mail`` en la ruta dada y devuelve el texto observable.

    Registra los mocks HTTP con ``responses``, invoca ``send_mail`` y recolecta
    todas las superficies que el módulo expone al llamador: el ``repr`` y el
    ``message`` del ``SendResult`` en rutas sin excepción, y el ``str`` de la
    excepción cuando corresponde. Devuelve la concatenación de esas superficies.
    """
    token_url = _token_url(config.tenant_id)
    graph_url = _graph_url(config.sender_mailbox)

    surfaces: list[str] = []

    with responses.RequestsMock() as rsps:
        if route == _TOKEN_FAILURE:
            # El endpoint de token falla: no se expone access_token ni cuerpo.
            rsps.add(rsps.POST, token_url, json={"error": "invalid_client"}, status=401)
        else:
            rsps.add(
                rsps.POST,
                token_url,
                json={"access_token": access_token, "expires_in": 3600},
                status=200,
            )
            graph_status = 202 if route == _SUCCESS else 403
            rsps.add(
                rsps.POST,
                graph_url,
                status=graph_status,
                headers={"request-id": "corr-id-1234"},
            )

        try:
            result = send_mail(
                "Prueba de integración Microsoft Graph",
                "Correo de prueba técnica automatizada.",
                "destinatario@example.com",
                config=config,
            )
        except TokenError as exc:
            surfaces.append(str(exc))
            surfaces.append(repr(exc))
        else:
            surfaces.append(result.message)
            surfaces.append(repr(result))

    return "\n".join(surfaces)


@settings(
    max_examples=150,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    tenant_id=_secret_values,
    client_id=_secret_values,
    client_secret=_secret_values,
    access_token=_secret_values,
    route=_routes,
)
def test_no_secret_appears_in_module_output_or_errors(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    route: str,
    caplog,
) -> None:
    """Feature: graph-test-email, Property 5: Ningún secreto aparece en la salida ni en los errores del módulo.

    Validates: Requirements 2.4, 3.2
    """
    config = MailerConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        # El buzón y el destinatario NO son secretos; valores fijos y sin marker.
        sender_mailbox="phishing@itau.cl",
        test_recipient="qa@example.com",
    )

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="graph_mailer"):
        surfaces = _collect_secret_surfaces(config, access_token, route)

    # Incluir cualquier registro de logging emitido por el módulo.
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    observable = surfaces + "\n" + log_text

    secrets = {
        "GRAPH_TENANT_ID": tenant_id,
        "GRAPH_CLIENT_ID": client_id,
        "GRAPH_CLIENT_SECRET": client_secret,
        "Access_Token": access_token,
    }
    for name, value in secrets.items():
        assert value not in observable, (
            f"El Secret_Value {name!r} se filtró en la salida/errores del módulo "
            f"(ruta={route!r})."
        )
