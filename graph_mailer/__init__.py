"""graph_mailer — integración con Microsoft Graph para envío de correos de prueba técnica.

Este paquete expone la API pública reutilizable del Mail_Module. Otro proyecto
puede importar directamente desde ``graph_mailer``::

    from graph_mailer import send_mail, MailerConfig, SendResult
    from graph_mailer import MailerError, MissingConfigError, TokenError, GraphError

API pública:

- ``send_mail(subject, body, to, *, config=None)``: envía un correo vía Microsoft
  Graph desde el ``Sender_Mailbox`` configurado y retorna un ``SendResult``.
- ``MailerConfig`` / ``load_config``: configuración inmutable y su cargador desde
  el entorno o un archivo ``.env``.
- ``SendResult``: resultado de ``send_mail`` (diagnóstico seguro, sin secretos).
- ``TokenResult`` / ``GraphResponse``: tipos de resultado de los clientes de token
  y de Graph, útiles al reutilizar los componentes de bajo nivel.
- Jerarquía de errores: ``MailerError`` (base), ``MissingConfigError``,
  ``TokenError`` y ``GraphError``, para que el llamador pueda capturarlos.

Principio de seguridad: ningún ``Secret_Value`` aparece jamás en la salida ni en
los mensajes de error producidos por el paquete.
"""

from __future__ import annotations

from .config import MailerConfig, load_config
from .errors import GraphError, MailerError, MissingConfigError, TokenError
from .graph import GraphResponse
from .mailer import SendResult, send_mail
from .token import TokenResult

__all__ = [
    # API principal
    "send_mail",
    "SendResult",
    # Configuración
    "MailerConfig",
    "load_config",
    # Tipos de resultado de los clientes de bajo nivel
    "TokenResult",
    "GraphResponse",
    # Jerarquía de errores
    "MailerError",
    "MissingConfigError",
    "TokenError",
    "GraphError",
]
