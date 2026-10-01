"""Property-based tests del Config_Loader.

Feature: graph-test-email, Property 3: Configuración cargada desde el entorno

Valida que, para cualquier mapping de entorno que contenga todas las variables
requeridas, ``load_config`` produce una ``MailerConfig`` cuyos campos coinciden
exactamente con los valores provistos en ese mapping. El mapping se inyecta vía
``load_config(env=...)`` para no tocar ``os.environ`` ni el ``.env`` real.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from graph_mailer.config import load_config

# ``load_config`` trata un valor vacío como ausente (``not env.get(name)``), por
# lo que las variables requeridas deben generarse con texto no vacío. Permitimos
# un amplio rango de caracteres Unicode para ejercitar la lógica con fuerza.
_required_value = st.text(min_size=1, max_size=64).filter(lambda s: s != "")

# El destinatario de prueba es opcional para el módulo; puede ser vacío.
_recipient_value = st.text(min_size=0, max_size=64)


@settings(max_examples=200)
@given(
    tenant_id=_required_value,
    client_id=_required_value,
    client_secret=_required_value,
    sender_mailbox=_required_value,
    test_recipient=_recipient_value,
)
def test_load_config_matches_env_mapping(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    sender_mailbox: str,
    test_recipient: str,
) -> None:
    """Feature: graph-test-email, Property 3: Configuración cargada desde el entorno.

    Validates: Requirements 3.1
    """
    env = {
        "GRAPH_TENANT_ID": tenant_id,
        "GRAPH_CLIENT_ID": client_id,
        "GRAPH_CLIENT_SECRET": client_secret,
        "GRAPH_SENDER_MAILBOX": sender_mailbox,
        "GRAPH_TEST_RECIPIENT": test_recipient,
    }

    config = load_config(env=env)

    assert config.tenant_id == tenant_id
    assert config.client_id == client_id
    assert config.client_secret == client_secret
    assert config.sender_mailbox == sender_mailbox
    assert config.test_recipient == test_recipient
