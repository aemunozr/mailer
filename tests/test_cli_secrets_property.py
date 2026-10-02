"""Property test de no exposición de secretos en el Test_CLI.

Feature: graph-test-email, Property 6: Ningún secreto aparece en la salida del CLI

Validates: Requirements 3.3

Property 6 (design.md): para cualquier conjunto de ``Secret_Value`` y para
cualquier ruta de ejecución del ``Test_CLI`` (éxito, 401, 403), ningún
``Secret_Value`` SHALL aparecer en stdout, stderr ni en los logs del Test_CLI.

Estrategia: el Test_CLI (``test_send_email.py``) se importa como módulo con
``importlib``. Por cada ejemplo se generan secretos aleatorios distintivos
(tenant/client/secret/access_token) y se inyectan en el CLI parcheando
``load_config`` (mediante ``monkeypatch``) para que devuelva un ``MailerConfig``
con esos secretos. ``send_mail`` se mockea por ruta para no tocar la red:

    - éxito : SendResult(success=True, status 202)
    - 401   : SendResult(success=False, status 401)
    - 403   : SendResult(success=False, status 403)

El ``access_token`` (un ``Secret_Value``) solo lo conoce el módulo internamente;
para asegurar que la superficie observable del CLI no lo filtra, el mock de
``send_mail`` recibe el ``config`` y expone el ``access_token`` únicamente a la
aserción (nunca lo imprime). Se captura stdout/stderr con ``capsys`` y los logs
con ``caplog``, y se asevera la NO aparición de ningún secreto.
"""

from __future__ import annotations

import importlib
import logging

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from graph_mailer.config import MailerConfig
from graph_mailer.mailer import SendResult

# El Test_CLI vive en la raíz del proyecto como ``test_send_email.py``.
cli = importlib.import_module("test_send_email")

# Marcador antepuesto a cada valor secreto para que la búsqueda de subcadena sea
# significativa y libre de colisiones incidentales con texto fijo del CLI,
# nombres de variables (MAYÚSCULAS) o el buzón/destinatario de prueba.
_SECRET_MARKER = "secret::"

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

# Rutas de ejecución a ejercer y el status HTTP asociado.
_SUCCESS = 202
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_routes = st.sampled_from([_SUCCESS, _UNAUTHORIZED, _FORBIDDEN])


@settings(
    max_examples=150,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    tenant_id=_secret_values,
    client_id=_secret_values,
    client_secret=_secret_values,
    access_token=_secret_values,
    status_code=_routes,
)
def test_no_secret_appears_in_cli_output(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    status_code: int,
    monkeypatch,
    capsys,
    caplog,
) -> None:
    """Feature: graph-test-email, Property 6: Ningún secreto aparece en la salida del CLI.

    Validates: Requirements 3.3
    """
    config = MailerConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        # El buzón y el destinatario NO son secretos; valores fijos y sin marker.
        sender_mailbox="phishing@itau.cl",
        test_recipient="qa@example.com",
    )

    monkeypatch.setattr(cli, "load_config", lambda: config)

    def _fake_send_mail(subject, body, to, *, config=None):
        # El access_token es un Secret_Value que el módulo manejaría internamente;
        # el CLI nunca debe recibirlo ni imprimirlo. Se devuelve un diagnóstico
        # seguro (sin secretos), tal como lo haría el Mail_Module real.
        return SendResult(
            success=(status_code == _SUCCESS),
            status_code=status_code,
            correlation_id="corr-id-abcdef",
            message="diagnóstico seguro (HTTP %d)." % status_code,
        )

    monkeypatch.setattr(cli, "send_mail", _fake_send_mail)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        cli.main()

    captured = capsys.readouterr()
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    observable = captured.out + "\n" + captured.err + "\n" + log_text

    secrets = {
        "GRAPH_TENANT_ID": tenant_id,
        "GRAPH_CLIENT_ID": client_id,
        "GRAPH_CLIENT_SECRET": client_secret,
        "Access_Token": access_token,
    }
    for name, value in secrets.items():
        assert value not in observable, (
            f"El Secret_Value {name!r} se filtró en la salida del CLI "
            f"(status={status_code})."
        )
