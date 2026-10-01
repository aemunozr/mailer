"""Config_Loader del Mail_Module.

Lee la configuración exclusivamente desde variables de entorno o desde el
``Env_File`` (``.env``, cargado con ``python-dotenv``). Expone ``MailerConfig``
(dataclass inmutable con ``__repr__`` enmascarado) y ``load_config``.

Principio de seguridad: ningún ``Secret_Value`` (``tenant_id``, ``client_id``,
``client_secret``, Access_Token) aparece jamás en ``repr``/logs/salida ni en los
mensajes de error producidos por este módulo. Ante variables ausentes se lanza
un único ``MissingConfigError`` que nombra las variables faltantes, nunca sus
valores.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import MissingConfigError

__all__ = ["MailerConfig", "load_config"]

# Nombres de variables de entorno requeridas por el Mail_Module.
# ``GRAPH_TEST_RECIPIENT`` NO es requerido por el módulo (solo por el Test_CLI),
# por eso no aparece aquí; ver design.md (Config_Loader).
_ENV_TENANT_ID = "GRAPH_TENANT_ID"
_ENV_CLIENT_ID = "GRAPH_CLIENT_ID"
_ENV_CLIENT_SECRET = "GRAPH_CLIENT_SECRET"
_ENV_SENDER_MAILBOX = "GRAPH_SENDER_MAILBOX"
_ENV_TEST_RECIPIENT = "GRAPH_TEST_RECIPIENT"

# Variables requeridas por el módulo (en orden estable para mensajes de error).
_REQUIRED_VARS = (
    _ENV_TENANT_ID,
    _ENV_CLIENT_ID,
    _ENV_CLIENT_SECRET,
    _ENV_SENDER_MAILBOX,
)


@dataclass(frozen=True)
class MailerConfig:
    """Configuración inmutable del Mail_Module.

    ``tenant_id``, ``client_id`` y ``client_secret`` son ``Secret_Value`` y nunca
    deben mostrarse; por eso ``__repr__`` los enmascara. ``sender_mailbox`` y
    ``test_recipient`` no son secretos.
    """

    tenant_id: str
    client_id: str
    client_secret: str
    sender_mailbox: str
    test_recipient: str = ""

    def __repr__(self) -> str:
        return (
            "MailerConfig(tenant_id=***, client_id=***, "
            "client_secret=***, sender_mailbox=%r, test_recipient=%r)"
            % (self.sender_mailbox, self.test_recipient)
        )


def load_config(env: Mapping[str, str] | None = None) -> MailerConfig:
    """Carga la configuración del Mail_Module desde el entorno o un ``.env``.

    Si no se inyecta ``env``, se cargan primero las variables del ``Env_File`` con
    ``python-dotenv`` (sin sobrescribir las ya presentes en el entorno real) y
    luego se lee de ``os.environ``. Se acepta un ``Mapping`` ``env`` inyectable
    para pruebas; en ese caso ``load_dotenv`` no se invoca.

    Recolecta TODAS las variables requeridas ausentes y lanza un único
    ``MissingConfigError`` que las nombra, sin exponer ningún valor.

    ``GRAPH_TEST_RECIPIENT`` es opcional para el módulo (lo usa el Test_CLI); si
    está presente se incluye en la configuración, y si falta queda vacío.
    """
    if env is None:
        # Carga diferida: solo se importa/usa dotenv cuando se lee del entorno real.
        from dotenv import load_dotenv

        load_dotenv()
        env = os.environ

    missing = [name for name in _REQUIRED_VARS if not env.get(name)]
    if missing:
        # Mensaje con texto fijo + nombres de variables; nunca valores.
        raise MissingConfigError(
            "Faltan variables de configuración requeridas: " + ", ".join(missing)
        )

    return MailerConfig(
        tenant_id=env[_ENV_TENANT_ID],
        client_id=env[_ENV_CLIENT_ID],
        client_secret=env[_ENV_CLIENT_SECRET],
        sender_mailbox=env[_ENV_SENDER_MAILBOX],
        test_recipient=env.get(_ENV_TEST_RECIPIENT, ""),
    )
