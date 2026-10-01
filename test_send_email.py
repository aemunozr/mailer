#!/usr/bin/env python3
"""Test_CLI — script de prueba aislado de la integración con Microsoft Graph.

Este NO es un test de pytest: es un script ejecutable (``main``) que orquesta el
Mail_Module y emite diagnóstico por paso. Se estructura con ``def main() -> int``
y el guard ``if __name__ == "__main__": raise SystemExit(main())`` para que
pytest no lo recolecte como caso de prueba (no hay funciones ``test_*`` a nivel
superior).

Flujo (ver design.md, Test_CLI):

1. Carga la configuración desde el entorno/``.env`` con ``load_config``.
2. Usa ``GRAPH_TEST_RECIPIENT`` como destinatario.
3. Compone un asunto y un cuerpo inequívocamente de prueba técnica, SIN elementos
   de phishing (sin enlaces engañosos, sin solicitud de credenciales, sin
   suplantación de marca ni urgencia artificial).
4. Invoca ``send_mail(subject, body, to)`` UNA vez.
5. Emite diagnóstico por paso: confirmación de token obtenido (sin su valor),
   status HTTP y ``Correlation_Id``.
6. Traduce 401 a falla de autenticación y 403 a falta de permisos.
7. Código de salida: 0 en éxito (HTTP 202), distinto de 0 en fallo.

Principio de seguridad: ningún ``Secret_Value`` (TENANT_ID, CLIENT_ID,
CLIENT_SECRET, Access_Token) aparece jamás en stdout/stderr. El diagnóstico se
compone solo con texto fijo + metadatos no sensibles (status HTTP, correlation
id, nombres de variables).
"""

from __future__ import annotations

import sys

from graph_mailer import load_config, send_mail
from graph_mailer.errors import GraphError, MissingConfigError, TokenError

# Códigos de salida del CLI (0 = éxito; cualquier otro = fallo).
_EXIT_OK = 0
_EXIT_CONFIG_ERROR = 2
_EXIT_TOKEN_ERROR = 3
_EXIT_GRAPH_ERROR = 4
_EXIT_SEND_FAILED = 5

# Status HTTP relevantes para el diagnóstico.
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403

# Contenido del correo de prueba (anti-phishing): identifica el mensaje de forma
# inequívoca como una validación automatizada de integración técnica.
_SUBJECT = "Prueba de integración Microsoft Graph"
_BODY = (
    "Este es un correo de prueba técnica generado automáticamente para validar "
    "la integración con Microsoft Graph. Corresponde a una validación "
    "automatizada de la conectividad y los permisos de la aplicación. No "
    "requiere ninguna acción del destinatario y puede ignorarse."
)


def _print_auth_failure() -> None:
    """Mensaje de diagnóstico para un status HTTP 401 (falla de autenticación)."""
    print(
        "      Falla de autenticación: revise GRAPH_TENANT_ID / GRAPH_CLIENT_ID "
        "/ GRAPH_CLIENT_SECRET."
    )


def _print_permission_failure() -> None:
    """Mensaje de diagnóstico para un status HTTP 403 (falta de permisos)."""
    print(
        "      Falta de permisos: la aplicación requiere el permiso de "
        "aplicación Mail.Send (consentido por un administrador)."
    )


def main() -> int:
    """Punto de entrada del Test_CLI. Devuelve el código de salida del proceso."""
    # [1/3] Configuración.
    print("[1/3] Cargando configuración desde entorno/.env...", end=" ")
    try:
        config = load_config()
    except MissingConfigError as exc:
        # El mensaje de MissingConfigError nombra las variables ausentes, nunca
        # sus valores: es seguro mostrarlo.
        print("ERROR")
        print("      " + str(exc))
        return _EXIT_CONFIG_ERROR

    recipient = config.test_recipient
    if not recipient:
        print("ERROR")
        print(
            "      Falta la variable requerida por el CLI: GRAPH_TEST_RECIPIENT."
        )
        return _EXIT_CONFIG_ERROR
    print("OK")

    # [2/3] + [3/3] Obtención de token y envío. ``send_mail`` encapsula ambos
    # pasos; se anuncia la obtención del token ANTES de la llamada (sin su valor)
    # y, si todo va bien, se confirma a continuación.
    print("[2/3] Obteniendo token (client credentials)...", end=" ")
    try:
        result = send_mail(_SUBJECT, _BODY, recipient, config=config)
    except TokenError as exc:
        # Falla al obtener el token. Un 401 del endpoint de token se traduce a
        # falla de autenticación. ``exc`` nunca contiene un Secret_Value.
        print("ERROR")
        print("      " + str(exc))
        if exc.status_code == _HTTP_UNAUTHORIZED:
            _print_auth_failure()
        return _EXIT_TOKEN_ERROR
    except GraphError as exc:
        # Falla de transporte frente a Graph (no 401/403). Mensaje sin secretos.
        print("OK (token obtenido)")
        print("[3/3] Enviando correo vía Microsoft Graph...")
        print("      " + str(exc))
        return _EXIT_GRAPH_ERROR

    # Si llegamos aquí, el token se obtuvo correctamente (send_mail no falló al
    # pedirlo) y ya tenemos la respuesta de sendMail.
    print("OK (token obtenido)")

    # [3/3] Resultado del envío: status HTTP + Correlation_Id (Req 4.3).
    print("[3/3] Enviando correo vía Microsoft Graph...")
    correlation = result.correlation_id if result.correlation_id else "(no disponible)"
    print("      HTTP %d  correlation-id: %s" % (result.status_code, correlation))

    if result.success:
        print("      Resultado: ÉXITO — correo de prueba enviado a %s" % recipient)
        return _EXIT_OK

    # Fallo: traducir 401/403 a mensajes legibles.
    if result.status_code == _HTTP_UNAUTHORIZED:
        _print_auth_failure()
    elif result.status_code == _HTTP_FORBIDDEN:
        _print_permission_failure()
    else:
        print("      Resultado: FALLO — " + result.message)
    return _EXIT_SEND_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
