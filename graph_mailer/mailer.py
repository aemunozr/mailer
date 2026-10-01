"""API pública del Mail_Module.

Expone ``SendResult`` (dataclass inmutable con diagnóstico seguro) y la función
pública ``send_mail(subject, body, to)``, que orquesta la carga de configuración,
la obtención del ``Access_Token`` y el envío vía Microsoft Graph.

Contrato de diseño (ver design.md, Mail_Module API pública):

1. Carga la configuración con ``load_config()`` si no se inyecta ``config``.
2. Obtiene el ``Access_Token`` con ``fetch_token`` (Token_Client).
3. Envía el correo con ``send_via_graph`` (Graph_Client) mediante
   ``POST /v1.0/users/{Sender_Mailbox}/sendMail``.
4. Retorna un ``SendResult`` indicando éxito (status HTTP 202) o fallo.

El remitente SIEMPRE es ``config.sender_mailbox``; nunca se toma del llamador.

Principio de seguridad: ningún ``Secret_Value`` (``tenant_id``, ``client_id``,
``client_secret``, Access_Token) aparece jamás en el campo ``message`` del
``SendResult`` ni en ninguna otra salida de este módulo. El diagnóstico se compone
solo con texto fijo + metadatos no sensibles (status HTTP, correlation id).
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import MailerConfig, load_config
from .graph import send_via_graph
from .token import fetch_token

__all__ = ["SendResult", "send_mail"]

# Status HTTP que Microsoft Graph devuelve ante un ``sendMail`` aceptado.
_SUCCESS_STATUS = 202


@dataclass(frozen=True)
class SendResult:
    """Resultado de un intento de envío vía ``send_mail``.

    ``success`` es ``True`` solo cuando el status HTTP es 202. ``status_code`` y
    ``correlation_id`` provienen de la respuesta de Graph. ``message`` es texto de
    diagnóstico SEGURO: nunca contiene un ``Secret_Value``.
    """

    success: bool
    status_code: int
    correlation_id: str | None
    message: str


def send_mail(
    subject: str,
    body: str,
    to: str,
    *,
    config: MailerConfig | None = None,
) -> SendResult:
    """Envía un correo vía Microsoft Graph desde el ``Sender_Mailbox`` configurado.

    Args:
        subject: Asunto del correo.
        body: Cuerpo del correo (texto plano).
        to: Destinatario del correo.
        config: Configuración opcional a inyectar (útil para pruebas y para la
            reutilización desde otro proyecto que ya tenga su configuración
            cargada). Si es ``None`` se carga con ``load_config()``.

    Returns:
        ``SendResult`` con ``success=True`` si el status HTTP es 202, o
        ``success=False`` en cualquier otro caso. El campo ``message`` contiene
        diagnóstico seguro sin ningún ``Secret_Value``.

    Notas:
        El remitente SIEMPRE es ``config.sender_mailbox``; no se toma del
        llamador. Las posibles excepciones de los componentes subyacentes
        (``MissingConfigError``, ``TokenError``, ``GraphError``) se propagan al
        llamador tal cual, con mensajes libres de secretos.
    """
    if config is None:
        config = load_config()

    token = fetch_token(config)

    response = send_via_graph(
        token.access_token,
        config.sender_mailbox,
        subject,
        body,
        to,
    )

    success = response.status_code == _SUCCESS_STATUS
    if success:
        message = (
            "Correo enviado correctamente vía Microsoft Graph "
            "(HTTP %d)." % response.status_code
        )
    else:
        message = (
            "El envío vía Microsoft Graph no fue aceptado "
            "(HTTP %d)." % response.status_code
        )

    return SendResult(
        success=success,
        status_code=response.status_code,
        correlation_id=response.correlation_id,
        message=message,
    )
