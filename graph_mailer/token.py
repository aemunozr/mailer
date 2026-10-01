"""Token_Client del Mail_Module.

Solicita un ``Access_Token`` al endpoint de token OAuth2 de Entra ID mediante el
flujo *client credentials* usando la biblioteca ``requests`` (sin
``azure-identity`` ni ``msgraph-sdk``). Expone ``TokenResult`` (dataclass
inmutable) y ``fetch_token``.

Principio de seguridad: ningún ``Secret_Value`` (``tenant_id``, ``client_id``,
``client_secret``, Access_Token) ni cuerpo crudo sensible de la respuesta aparece
jamás en logs, salida o mensajes de error. Ante fallas se lanza ``TokenError``
con un mensaje genérico más el status HTTP del endpoint de token (si está
disponible) para diagnóstico.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import MailerConfig
from .errors import TokenError

__all__ = ["TokenResult", "fetch_token"]

# Plantilla del endpoint de token OAuth2 de Entra ID (v2.0, client credentials).
_TOKEN_ENDPOINT_TEMPLATE = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
)

# Scope app-only para Microsoft Graph (.default consolida los permisos de app).
_GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"


@dataclass(frozen=True)
class TokenResult:
    """Resultado de una obtención de token exitosa.

    ``access_token`` es un ``Secret_Value`` y NUNCA debe loggearse ni mostrarse.
    """

    access_token: str
    expires_in: int


def fetch_token(
    config: MailerConfig,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
) -> TokenResult:
    """Obtiene un ``Access_Token`` vía *client credentials*.

    Hace ``POST`` al endpoint de token del tenant configurado con
    ``Content-Type: application/x-www-form-urlencoded`` y el cuerpo
    ``grant_type=client_credentials``, ``client_id``, ``client_secret`` y
    ``scope=https://graph.microsoft.com/.default``.

    Args:
        config: Configuración con las credenciales del tenant.
        session: ``requests.Session`` opcional (útil para pruebas/reuso). Si no
            se provee, se usa ``requests.post`` directamente.
        timeout: Timeout en segundos para la solicitud HTTP (siempre explícito).

    Returns:
        ``TokenResult`` con el ``access_token`` y su ``expires_in``.

    Raises:
        TokenError: Si la respuesta no es 2xx o no contiene ``access_token``. El
            mensaje es genérico e incluye el status HTTP cuando está disponible;
            nunca contiene ``client_secret``, ``tenant_id``, ``client_id`` ni el
            cuerpo crudo de la respuesta.
    """
    endpoint = _TOKEN_ENDPOINT_TEMPLATE.format(tenant_id=config.tenant_id)
    data = {
        "grant_type": "client_credentials",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "scope": _GRAPH_DEFAULT_SCOPE,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    poster = session.post if session is not None else requests.post
    response = poster(endpoint, data=data, headers=headers, timeout=timeout)

    status_code = response.status_code
    if not 200 <= status_code < 300:
        # Mensaje genérico + status HTTP; nunca el cuerpo crudo ni secretos.
        raise TokenError(
            "Falla de obtención de token desde el endpoint de Entra ID.",
            status_code=status_code,
        )

    try:
        payload = response.json()
    except ValueError:
        payload = None

    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not access_token:
        raise TokenError(
            "Falla de obtención de token: la respuesta no contiene access_token.",
            status_code=status_code,
        )

    expires_in = payload.get("expires_in", 0) if isinstance(payload, dict) else 0
    try:
        expires_in = int(expires_in)
    except (TypeError, ValueError):
        expires_in = 0

    return TokenResult(access_token=access_token, expires_in=expires_in)
