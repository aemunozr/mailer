"""Property test del Config_Loader: variable ausente reportada por nombre.

Feature: graph-test-email, Property 4: Variable de configuración ausente es
reportada por nombre

Validates: Requirements 3.4

Property 4 (design.md): Para cualquier subconjunto no vacío de variables
requeridas que se omita del entorno, ``load_config`` SHALL lanzar un
``MissingConfigError`` que nombre CADA variable ausente y que no contenga el
valor de ningún ``Secret_Value``.

Las variables requeridas por el módulo son las cuatro siguientes
(``GRAPH_TEST_RECIPIENT`` NO es requerido por el módulo):
    - GRAPH_TENANT_ID
    - GRAPH_CLIENT_ID
    - GRAPH_CLIENT_SECRET
    - GRAPH_SENDER_MAILBOX
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from graph_mailer.config import load_config
from graph_mailer.errors import MissingConfigError

# Variables requeridas por el Mail_Module. GRAPH_TEST_RECIPIENT se omite a
# propósito: no es requerido por el módulo.
REQUIRED_VARS = (
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_CLIENT_SECRET",
    "GRAPH_SENDER_MAILBOX",
)

# Variables cuyo valor es un Secret_Value y por tanto nunca debe aparecer en el
# mensaje de error.
SECRET_VARS = frozenset(
    {"GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"}
)

# Marcador único antepuesto a cada valor "secreto" generado. Contiene ``::`` y
# minúsculas, caracteres que NO aparecen en ninguna de las variables requeridas
# (todas en MAYÚSCULAS con guiones bajos). Esto garantiza que un valor secreto
# jamás pueda ser subcadena incidental de un nombre de variable presente en el
# mensaje de error, evitando falsos positivos (p. ej. "L" dentro de
# "GRAPH_CLIENT_ID").
_SECRET_MARKER = "secret::"

# Nombres de todas las variables requeridas, usados para descartar cualquier
# texto base que pudiera ser subcadena de un nombre (defensa adicional).
_ALL_NAMES = "\n".join(REQUIRED_VARS)

# Generador de valores de configuración "secretos": cada valor lleva un
# marcador distintivo al inicio y un cuerpo de texto imprimible sin comas (para
# no confundir con el separador del mensaje). El marcador hace que la búsqueda
# de subcadena sea significativa y libre de colisiones con los nombres.
_secret_bodies = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126, blacklist_characters=","),
    min_size=1,
    max_size=40,
).filter(lambda body: body not in _ALL_NAMES)

_secret_values = _secret_bodies.map(lambda body: _SECRET_MARKER + body)

# Subconjunto NO vacío de las variables requeridas a omitir del entorno.
_subsets_to_omit = st.lists(
    st.sampled_from(REQUIRED_VARS),
    min_size=1,
    max_size=len(REQUIRED_VARS),
    unique=True,
).map(sorted)


@settings(max_examples=200)
@given(
    omit=_subsets_to_omit,
    values=st.fixed_dictionaries(
        {name: _secret_values for name in REQUIRED_VARS}
    ),
)
def test_missing_vars_reported_by_name_without_secret_values(omit, values):
    """Property 4: el error nombra cada variable ausente y no filtra secretos."""
    omit_set = set(omit)

    # Entorno con TODAS las variables requeridas, excepto las omitidas.
    env = {name: value for name, value in values.items() if name not in omit_set}

    with pytest.raises(MissingConfigError) as exc_info:
        load_config(env=env)

    message = str(exc_info.value)

    # El error DEBE nombrar cada variable ausente.
    for name in omit_set:
        assert name in message, (
            f"La variable ausente {name!r} no aparece en el mensaje de error: {message!r}"
        )

    # Ninguna variable presente debe reportarse como ausente.
    present = set(REQUIRED_VARS) - omit_set
    for name in present:
        assert name not in message, (
            f"La variable presente {name!r} fue reportada como ausente: {message!r}"
        )

    # El mensaje NUNCA debe contener el valor de ningún Secret_Value, ni
    # siquiera el de una variable secreta que esté presente en el entorno.
    for name in SECRET_VARS:
        secret_value = values[name]
        assert secret_value not in message, (
            f"El valor del Secret_Value {name!r} se filtró en el mensaje de error."
        )


def test_all_vars_omitted_names_all_of_them():
    """Edge case: omitir TODAS las requeridas nombra las cuatro variables."""
    with pytest.raises(MissingConfigError) as exc_info:
        load_config(env={})

    message = str(exc_info.value)

    for name in REQUIRED_VARS:
        assert name in message
