"""Jerarquía de errores del dominio del Mail_Module.

Principio transversal de seguridad: NINGÚN mensaje de error construido por
estas clases contiene jamás un ``Secret_Value`` (TENANT_ID, CLIENT_ID,
CLIENT_SECRET ni el Access_Token). Los mensajes se componen únicamente con
texto fijo + metadatos no sensibles (nombres de variables, status HTTP,
correlation id).
"""

from __future__ import annotations

__all__ = [
    "MailerError",
    "MissingConfigError",
    "TokenError",
    "GraphError",
]


class MailerError(Exception):
    """Base de todos los errores del Mail_Module.

    Los mensajes de esta clase y de todas sus subclases NUNCA contienen un
    ``Secret_Value`` (TENANT_ID, CLIENT_ID, CLIENT_SECRET ni Access_Token).
    """


class MissingConfigError(MailerError):
    """Falta una o más variables de configuración requeridas.

    Nombra las variables ausentes por nombre; NUNCA incluye el valor de ningún
    ``Secret_Value``.
    """


class TokenError(MailerError):
    """Falla al obtener el Access_Token.

    Incluye el status HTTP del endpoint de token si está disponible, para
    diagnóstico (p.ej. 401). NUNCA incluye ``client_secret``, ``tenant_id``,
    ``client_id`` ni cuerpos crudos sensibles; es decir, nunca expone un
    ``Secret_Value``.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphError(MailerError):
    """Falla de transporte frente a Microsoft Graph.

    No se usa para 401/403 (esos se devuelven como ``GraphResponse`` para
    diagnóstico), sino para fallas de transporte (p.ej. timeouts o errores de
    red). NUNCA incluye el Access_Token ni ningún otro ``Secret_Value``.
    """
