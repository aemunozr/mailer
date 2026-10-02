# Implementation Plan: graph-test-email

## Overview

Implementación incremental en Python de la integración con Microsoft Graph (envío de correos de prueba técnica vía OAuth2 client credentials). Se construye primero la base del proyecto (dependencias, errores, configuración), luego los clientes HTTP (token y graph) con sus property tests, después la API pública `send_mail`, y finalmente el `Test_CLI` que orquesta y emite diagnóstico seguro. Todo el transporte HTTP se mockea en pruebas; ningún secreto aparece en logs ni salida. Lenguaje: Python.

## Tasks

- [x] 1. Establecer estructura del proyecto y base de seguridad
  - Crear el paquete `graph_mailer/` con `__init__.py` (exportará `send_mail` y tipos públicos una vez implementados)
  - Crear `requirements.txt` con dependencias fijadas: `requests==2.32.3`, `python-dotenv==1.0.1`
  - Crear `.gitignore` que incluya `.env`
  - Crear `.env.example` con las claves sin valores reales (`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_MAILBOX`, `GRAPH_TEST_RECIPIENT`)
  - Configurar framework de pruebas (`pytest`, `hypothesis`, `responses`) en `requirements-dev.txt`
  - _Requirements: 6.1, 6.2, 3.5_

- [x] 2. Implementar jerarquía de errores del dominio
  - [x] 2.1 Crear `graph_mailer/errors.py`
    - Definir `MailerError` (base), `MissingConfigError`, `TokenError` (con status HTTP opcional), `GraphError`
    - Documentar en cada clase que los mensajes nunca contienen `Secret_Value`
    - _Requirements: 2.4, 3.4_

- [ ] 3. Implementar carga de configuración (Config_Loader)
  - [x] 3.1 Crear `graph_mailer/config.py` con `MailerConfig` y `load_config`
    - Definir `MailerConfig` (dataclass frozen) con `__repr__` que enmascara tenant_id/client_id/client_secret
    - Implementar `load_config(env=None)` que llama `load_dotenv()` y lee de `os.environ` por defecto, aceptando un `env` inyectable
    - Recolectar TODAS las variables requeridas ausentes y lanzar un único `MissingConfigError` nombrándolas, sin exponer valores
    - _Requirements: 3.1, 3.4_

  - [x] 3.2 Escribir property test de carga de configuración
    - **Feature: graph-test-email, Property 3: Configuración cargada desde el entorno**
    - **Validates: Requirements 3.1**

  - [x] 3.3 Escribir property test de variable ausente reportada por nombre
    - **Feature: graph-test-email, Property 4: Variable de configuración ausente es reportada por nombre**
    - **Validates: Requirements 3.4**

- [x] 4. Implementar Token_Client
  - [x] 4.1 Crear `graph_mailer/token.py` con `TokenResult` y `fetch_token`
    - Definir `TokenResult` (frozen) con `access_token` y `expires_in`
    - Implementar `fetch_token(config, *, session=None, timeout=30.0)` con `POST` a `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`, body `grant_type=client_credentials`, `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`
    - Lanzar `TokenError` (mensaje genérico + status HTTP) ante no-2xx o falta de `access_token`, sin incluir ningún `Secret_Value` ni cuerpo crudo sensible
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 4.2 Escribir property test de solicitud de token bien formada
    - **Feature: graph-test-email, Property 2: Solicitud de token bien formada**
    - **Validates: Requirements 2.1**

- [ ] 5. Implementar Graph_Client
  - [x] 5.1 Crear `graph_mailer/graph.py` con `GraphResponse` y `send_via_graph`
    - Definir `GraphResponse` (frozen) con `status_code` y `correlation_id`
    - Implementar `send_via_graph(access_token, sender_mailbox, subject, body, to, *, session=None, timeout=30.0)` con `POST` a `/v1.0/users/{sender_mailbox}/sendMail`, header `Authorization: Bearer`, payload `message` sin `ccRecipients`, `bccRecipients` ni `attachments` y `saveToSentItems: true`
    - Extraer `Correlation_Id` de headers `request-id`/`client-request-id`; devolver `GraphResponse` para 401/403 (no excepción); lanzar `GraphError` solo ante fallas de transporte, sin exponer el token
    - _Requirements: 1.2, 1.3, 1.4, 2.3_

  - [x] 5.2 Escribir property test de solicitud sendMail bien formada
    - **Feature: graph-test-email, Property 1: Solicitud sendMail bien formada**
    - **Validates: Requirements 1.2, 1.3, 1.4, 2.3**

- [x] 6. Checkpoint - Verificar clientes base
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implementar API pública send_mail (Mail_Module)
  - [x] 7.1 Crear `graph_mailer/mailer.py` con `SendResult` y `send_mail`
    - Definir `SendResult` (frozen) con `success`, `status_code`, `correlation_id`, `message` (texto seguro sin secretos)
    - Implementar `send_mail(subject, body, to, *, config=None)` que carga config (si no se inyecta), obtiene token vía `fetch_token`, envía vía `send_via_graph`, y retorna `SendResult` (éxito en 202)
    - Forzar que el remitente SIEMPRE sea `config.sender_mailbox`, nunca del llamador
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

  - [x] 7.2 Exportar API pública desde `graph_mailer/__init__.py`
    - Exportar `send_mail`, `MailerConfig`, `SendResult` y tipos de error
    - _Requirements: 1.1_

  - [x] 7.3 Escribir unit test de éxito de send_mail
    - Verificar `SendResult(success=True)` ante HTTP 202 con transporte mockeado
    - _Requirements: 1.5_

  - [x] 7.4 Escribir property test de no exposición de secretos en el módulo
    - **Feature: graph-test-email, Property 5: Ningún secreto aparece en la salida ni en los errores del módulo**
    - **Validates: Requirements 2.4, 3.2**

- [ ] 8. Implementar Test_CLI con diagnóstico y contenido anti-phishing
  - [x] 8.1 Crear `test_send_email.py`
    - Cargar config vía `load_config`; usar `GRAPH_TEST_RECIPIENT` como destinatario
    - Componer asunto `"Prueba de integración Microsoft Graph"` y cuerpo que declare explícitamente que es validación automatizada de integración, sin elementos de phishing (sin enlaces engañosos, sin solicitud de credenciales, sin suplantación ni urgencia artificial)
    - Invocar `send_mail(subject, body, to)` una vez y emitir diagnóstico por paso: confirmación de token obtenido (sin valor), status HTTP y `Correlation_Id`
    - Traducir 401 a mensaje de falla de autenticación y 403 a mensaje de falta de permisos; código de salida 0 en éxito (202), distinto de 0 en fallo
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3_

  - [x] 8.2 Escribir unit tests de diagnóstico del CLI
    - Verificar lectura de config + una invocación a `send_mail` (4.1), diagnóstico de token en éxito (4.2), mensaje de autenticación en 401 (4.4) y de permisos en 403 (4.5)
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

  - [x] 8.3 Escribir property test de status y Correlation_Id en la salida del CLI
    - **Feature: graph-test-email, Property 7: El CLI muestra status HTTP y Correlation_Id**
    - **Validates: Requirements 4.3**

  - [x] 8.4 Escribir property test de no exposición de secretos en el CLI
    - **Feature: graph-test-email, Property 6: Ningún secreto aparece en la salida del CLI**
    - **Validates: Requirements 3.3**

  - [x] 8.5 Escribir tests de contenido anti-phishing del CLI
    - Asunto de integración técnica (5.1), cuerpo de validación automatizada (5.2), ausencia de elementos de phishing (5.3) — complementado con revisión manual
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 9. Smoke / static checks de contrato y seguridad
  - [x] 9.1 Escribir smoke/static tests
    - `send_mail` existe e invocable con firma `(subject, body, to)` (1.1)
    - No se importan `azure-identity` ni `msgraph-sdk` (2.2)
    - `.gitignore` contiene `.env` (3.5)
    - `requirements.txt` existe con dependencias fijadas (6.1) e incluye `requests` y `python-dotenv` fijados (6.2)
    - _Requirements: 1.1, 2.2, 3.5, 6.1, 6.2_

- [x] 10. Checkpoint final - Verificar integración completa
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Las tareas marcadas con `*` son opcionales (pruebas) y pueden omitirse para un MVP más rápido; las tareas de implementación no deben marcarse como opcionales.
- Cada tarea referencia requisitos específicos para trazabilidad.
- Los checkpoints aseguran validación incremental.
- Los property tests validan propiedades universales de corrección (mínimo 100 iteraciones) y referencian su propiedad del diseño.
- Los unit/example tests validan escenarios concretos y edge cases; los smoke/static checks validan contrato y seguridad.
- Todo el transporte HTTP se mockea en pruebas (p.ej. `responses`/`requests-mock`).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "4.1", "5.1"] },
    { "id": 3, "tasks": ["4.2", "5.2", "7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4", "8.5", "9.1"] }
  ]
}
```
