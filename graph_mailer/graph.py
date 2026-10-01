"""Graph_Client del Mail_Module.

Envía el correo mediante ``POST /v1.0/users/{sender_mailbox}/sendMail`` de
Microsoft Graph usando el ``Access_Token`` como credencial Bearer. Expone
``GraphResponse`` (dataclass inmutable con ``status_code`` y ``correlation_id``)
y ``send_via_graph``.

Contrato de diseño (ver design.md, Graph_Client):

- Endpoint: ``https://graph.microsoft.com/v1.0/users/{sender_mailbox}/sendMail``.
- Headers: ``Authorization: Bearer {access_token}`` y
  ``Content-Type: application/json``.
- Payload: estructura ``message`` con ``subject``, ``body`` (``contentType: Text``)
  y un único ``toRecipients``; sin ``ccRecipients``, ``bccRecipients`` ni
  ``attachments``; a nivel raíz ``saveToSentItems: true``.
- 401/403 NO son excepción: se devuelven como ``GraphResponse`` para que el
  llamador traduzca el status a diagnóstico (auth / permisos).
- Solo las fallas de transporte (timeouts, errores de red) lanzan ``GraphError``.

Principio de seguridad: el ``Access_Token`` es un ``Secret_Value`` y NUNCA
aparece en logs, en la salida ni en los mensajes de error de este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from .errors import GraphError

__all__ = ["GraphResponse", "send_via_graph"]

# Base del endpoint sendMail de Microsoft Graph (v1.0).
_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0/users/{sender_mailbox}/sendMail"

# Headers de respuesta de los que se extrae el Correlation_Id, en orden de
# preferencia (ver design.md).
_CORRELATION_HEADERS = ("request-id", "client-request-id")


@dataclass(frozen=True)
class GraphResponse:
    """Resultado de una llamada a ``sendMail``.

    ``status_code`` es el status HTTP devuelto por Graph (p.ej. 202 en éxito,
    401/403 en fallas de autenticación/permisos). ``correlation_id`` proviene de
    los headers ``request-id``/``client-request-id`` y puede ser ``None`` si Graph
    no los incluye. Ninguno de estos campos es un ``Secret_Value``.
    """

    status_code: int
    correlation_id: str | None


def _build_payload(subject: str, body: str, to: str) -> dict:
    """Construye el payload ``sendMail`` sin cc/bcc/adjuntos.

    Un único destinatario, cuerpo de tipo ``Text`` y ``saveToSentItems: true`` a
    nivel raíz. No incluye ``ccRecipients``, ``bccRecipients`` ni ``attachments``.
    """
    return {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }


def _extract_correlation_id(headers: object) -> str | None:
    """Extrae el ``Correlation_Id`` de los headers de respuesta.

    Devuelve el primer valor presente entre ``request-id`` y
    ``client-request-id`` (los headers HTTP son case-insensitive en ``requests``),
    o ``None`` si ninguno está presente.
    """
    get = getattr(headers, "get", None)
    if get is None:
        return None
    for name in _CORRELATION_HEADERS:
        value = get(name)
        if value:
            return value
    return None


def send_via_graph(
    access_token: str,
    sender_mailbox: str,
    subject: str,
    body: str,
    to: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
) -> GraphResponse:
    """Construye y envía la solicitud ``sendMail`` a Microsoft Graph.

    Realiza ``POST`` contra
    ``/v1.0/users/{sender_mailbox}/sendMail`` con el header
    ``Authorization: Bearer {access_token}`` y el payload ``message`` (sin cc/bcc/
    adjuntos, ``saveToSentItems: true``). Devuelve una ``GraphResponse`` con el
    status HTTP y el ``Correlation_Id`` extraído de los headers.

    No lanza por 401/403: esos status se devuelven como ``GraphResponse`` para que
    el llamador (mailer/CLI) los traduzca a diagnóstico. Solo las fallas de
    transporte (timeouts, errores de red) lanzan ``GraphError``; su mensaje nunca
    incluye el ``Access_Token`` ni ningún otro ``Secret_Value``.
    """
    url = _GRAPH_BASE_URL.format(sender_mailbox=sender_mailbox)
    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json",
    }
    payload = _build_payload(subject, body, to)

    http = session if session is not None else requests

    try:
        response = http.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        # Falla de transporte: mensaje genérico, sin exponer el token ni el cuerpo.
        # No se encadena ``exc`` con ``from`` para evitar que un repr de la
        # solicitud/headers (que contiene el Bearer) se filtre en el traceback.
        raise GraphError(
            "Falla de transporte al enviar el correo vía Microsoft Graph: "
            + type(exc).__name__
        ) from None

    return GraphResponse(
        status_code=response.status_code,
        correlation_id=_extract_correlation_id(response.headers),
    )
