# Design Document

## Overview

Esta funcionalidad entrega una integración en Python para enviar correos de prueba técnica a través de Microsoft Graph API usando autenticación app-only (OAuth2 *client credentials*). La solución se divide en dos superficies:

1. **Mail_Module** — módulo limpio y reutilizable que expone `send_mail(subject, body, to)` y encapsula la carga de configuración, la obtención de token y el envío a Graph. Pensado para integrarse luego en otro proyecto.
2. **Test_CLI** — script de prueba aislado que lee la configuración del entorno, invoca al módulo y produce diagnóstico detallado por paso (token OK, status HTTP, correlation id, mensajes 401/403), sin exponer secretos.

La implementación usa `requests` directamente contra el endpoint de token OAuth2 de Entra ID y contra `POST /users/{mailbox}/sendMail` de Microsoft Graph. **No** se usa `azure-identity` ni `msgraph-sdk`. Todos los secretos se gestionan exclusivamente por variables de entorno o un archivo `.env` (vía `python-dotenv`) excluido de git, y nunca se registran sus valores.

El contenido del correo de prueba es inequívocamente identificable como una prueba técnica de integración: no imita, simula ni induce a engaño de tipo phishing.

### Design Goals

- **Reutilizable**: el módulo no depende del CLI; el CLI depende del módulo.
- **Seguro por defecto**: los secretos nunca aparecen en logs ni en salida estándar.
- **Diagnosticable**: cada paso del flujo emite diagnóstico claro para localizar fallas.
- **Reproducible**: dependencias fijadas en `requirements.txt`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Test_CLI                             │
│   (test_send_email.py) — orquesta y emite diagnóstico         │
└───────────────┬───────────────────────────────────────────────┘
                │ import
                ▼
┌─────────────────────────────────────────────────────────────┐
│                        Mail_Module (graph_mailer)             │
│                                                               │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐    │
│  │ Config_Loader│──▶│ Token_Client │──▶│  Graph_Client   │    │
│  │ config.py    │   │ token.py     │   │  graph.py       │    │
│  └──────────────┘   └──────────────┘   └─────────────────┘    │
│         ▲                   │                   │             │
│         └─────── send_mail(subject, body, to) ──┘             │
│                    (mailer.py — API pública)                  │
└───────────────┬───────────────────────┬───────────────────────┘
                │ requests (HTTP)        │ requests (HTTP)
                ▼                        ▼
   Entra ID OAuth2 token endpoint   Microsoft Graph
   /{tenant}/oauth2/v2.0/token      /v1.0/users/{mailbox}/sendMail
```

### Flujo de ejecución (happy path)

1. `Test_CLI` arranca y pide a `Config_Loader` la configuración desde entorno/`.env`.
2. `Test_CLI` llama `send_mail(subject, body, to)` del `Mail_Module`.
3. `send_mail` solicita a `Token_Client` un `Access_Token` (client credentials).
4. `Token_Client` hace `POST` al endpoint de token y devuelve el token (sin loggearlo).
5. `send_mail` pasa el token a `Graph_Client`, que hace `POST /users/{Sender_Mailbox}/sendMail` con `Authorization: Bearer`.
6. `Graph_Client` devuelve status HTTP (202 esperado) y `Correlation_Id`.
7. `send_mail` retorna un `SendResult` de éxito; `Test_CLI` imprime diagnóstico.

### Project Layout

```
Envio Correo/
├── graph_mailer/
│   ├── __init__.py        # exporta send_mail y tipos públicos
│   ├── config.py          # Config_Loader
│   ├── token.py           # Token_Client
│   ├── graph.py           # Graph_Client
│   ├── mailer.py          # API pública send_mail(subject, body, to)
│   └── errors.py          # excepciones/tipos de error del dominio
├── test_send_email.py     # Test_CLI
├── requirements.txt       # dependencias fijadas
├── .env.example           # plantilla sin secretos reales
├── .gitignore             # incluye .env
└── README.md
```

## Components and Interfaces

### Config_Loader (`config.py`)

Responsable de leer la configuración exclusivamente desde variables de entorno o desde el `Env_File` (`.env`), usando `python-dotenv` para cargar el archivo si existe. No obtiene valores de ninguna otra fuente.

Variables requeridas:

| Variable           | Descripción                                        | Secreto |
|--------------------|----------------------------------------------------|---------|
| `GRAPH_TENANT_ID`  | TENANT_ID del tenant de Entra ID                   | Sí      |
| `GRAPH_CLIENT_ID`  | CLIENT_ID de la aplicación registrada              | Sí      |
| `GRAPH_CLIENT_SECRET` | CLIENT_SECRET de la aplicación                  | Sí      |
| `GRAPH_SENDER_MAILBOX` | Buzón de origen fijo (`phishing@itau.cl`)      | No      |
| `GRAPH_TEST_RECIPIENT` | Destinatario de prueba (usado por el Test_CLI) | No      |

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class MailerConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    sender_mailbox: str
    test_recipient: str

    # __repr__ se sobreescribe para enmascarar secretos (nunca mostrar valores)
    def __repr__(self) -> str:
        return (
            "MailerConfig(tenant_id=***, client_id=***, "
            "client_secret=***, sender_mailbox=%r, test_recipient=%r)"
            % (self.sender_mailbox, self.test_recipient)
        )

def load_config(env: Mapping[str, str] | None = None) -> MailerConfig:
    """Carga la configuración desde el entorno (o un mapping inyectado para test).

    Lanza MissingConfigError nombrando CADA variable ausente, sin exponer valores.
    """
```

Notas de diseño:
- `load_config` acepta un `env` opcional para inyección en pruebas (por defecto `os.environ` tras `load_dotenv()`).
- La lista de requeridos para el módulo son las tres credenciales + `sender_mailbox`. `test_recipient` solo es requerido por el CLI; el módulo recibe `to` como argumento.
- El `__repr__` enmascarado evita fugas accidentales de secretos al imprimir/loggear el objeto.

### Token_Client (`token.py`)

Solicita un `Access_Token` al endpoint de token OAuth2 de Entra ID mediante *client credentials* usando `requests`.

- Endpoint: `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`
- Método: `POST` con `Content-Type: application/x-www-form-urlencoded`
- Body: `grant_type=client_credentials`, `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`

```python
@dataclass(frozen=True)
class TokenResult:
    access_token: str   # nunca se loggea
    expires_in: int

def fetch_token(config: MailerConfig, *, session=None, timeout: float = 30.0) -> TokenResult:
    """Obtiene un Access_Token vía client credentials.

    Lanza TokenError (sin incluir ningún Secret_Value) si la respuesta no es 2xx
    o no contiene access_token. El status HTTP del endpoint de token se adjunta
    al error para diagnóstico (p.ej. 401).
    """
```

Manejo de errores:
- Si el status no es 2xx o falta `access_token`, lanza `TokenError` con un mensaje genérico de "falla de obtención de token" y el status HTTP, **sin** incluir client_secret, tenant_id, client_id ni el cuerpo crudo que pudiera reflejar credenciales.

### Graph_Client (`graph.py`)

Envía el correo mediante `POST /users/{mailbox}/sendMail` de Microsoft Graph usando el `Access_Token` como credencial Bearer.

- Endpoint: `https://graph.microsoft.com/v1.0/users/{sender_mailbox}/sendMail`
- Método: `POST`
- Headers: `Authorization: Bearer {access_token}`, `Content-Type: application/json`
- Body: estructura `message` sin CC, BCC ni adjuntos.

```python
@dataclass(frozen=True)
class GraphResponse:
    status_code: int
    correlation_id: str | None   # de headers request-id / client-request-id

def send_via_graph(
    access_token: str,
    sender_mailbox: str,
    subject: str,
    body: str,
    to: str,
    *,
    session=None,
    timeout: float = 30.0,
) -> GraphResponse:
    """Construye y envía la solicitud sendMail. Devuelve status y Correlation_Id.

    No lanza por 401/403: devuelve la GraphResponse para que el llamador
    (mailer/CLI) traduzca el status a diagnóstico. Lanza GraphError solo ante
    fallas de transporte, sin exponer el token.
    """
```

Payload construido (sin cc/bcc/adjuntos):

```json
{
  "message": {
    "subject": "<subject>",
    "body": { "contentType": "Text", "content": "<body>" },
    "toRecipients": [ { "emailAddress": { "address": "<to>" } } ]
  },
  "saveToSentItems": true
}
```

El `Correlation_Id` se extrae de los headers de respuesta `request-id` o `client-request-id`.

### Mail_Module API pública (`mailer.py`)

```python
@dataclass(frozen=True)
class SendResult:
    success: bool
    status_code: int
    correlation_id: str | None
    message: str   # diagnóstico seguro, sin secretos

def send_mail(subject: str, body: str, to: str, *, config: MailerConfig | None = None) -> SendResult:
    """Envía un correo vía Microsoft Graph desde el Sender_Mailbox configurado.

    1. Carga config (si no se inyecta).
    2. Obtiene Access_Token (Token_Client).
    3. Envía vía Graph_Client (POST /users/{Sender_Mailbox}/sendMail).
    4. Retorna SendResult indicando éxito (status 202) o fallo, sin exponer secretos.

    El remitente SIEMPRE es config.sender_mailbox; no se toma del llamador.
    """
```

`send_mail` acepta `config` opcional para permitir inyección en pruebas y reutilización desde otro proyecto que ya tenga su configuración cargada. Por defecto llama `load_config()`.

### Test_CLI (`test_send_email.py`)

Script aislado que:
1. Carga configuración vía `Config_Loader`.
2. Compone subject/body de prueba técnica (ver Content Safety) y usa `GRAPH_TEST_RECIPIENT` como destinatario.
3. Invoca `send_mail(subject, body, to)`.
4. Emite diagnóstico por paso:
   - Confirmación de token obtenido (sin valor).
   - Status HTTP y `Correlation_Id` de la respuesta de `sendMail`.
   - En 401: mensaje de **falla de autenticación**.
   - En 403: mensaje de **falta de permisos de la aplicación**.
5. Código de salida: `0` en éxito (202), distinto de `0` en fallo.

Diagnóstico (ejemplo de salida, sin secretos):

```
[1/3] Cargando configuración desde entorno/.env... OK
[2/3] Obteniendo token (client credentials)... OK (token obtenido)
[3/3] Enviando correo vía Microsoft Graph...
      HTTP 202  correlation-id: 7f1a...-...-...
      Resultado: ÉXITO — correo de prueba enviado a <destinatario>
```

Para fallos:

```
      HTTP 401  correlation-id: ...
      Falla de autenticación: revise TENANT_ID / CLIENT_ID / CLIENT_SECRET.
```
```
      HTTP 403  correlation-id: ...
      Falta de permisos: la aplicación requiere el permiso de aplicación Mail.Send (consentido).
```

## Data Models

```python
# config.py
@dataclass(frozen=True)
class MailerConfig:
    tenant_id: str          # Secret_Value
    client_id: str          # Secret_Value
    client_secret: str      # Secret_Value
    sender_mailbox: str
    test_recipient: str

# token.py
@dataclass(frozen=True)
class TokenResult:
    access_token: str       # Secret_Value — nunca se loggea
    expires_in: int

# graph.py
@dataclass(frozen=True)
class GraphResponse:
    status_code: int
    correlation_id: str | None

# mailer.py
@dataclass(frozen=True)
class SendResult:
    success: bool
    status_code: int
    correlation_id: str | None
    message: str            # texto seguro para mostrar/loggear
```

## Error Handling

Jerarquía de errores en `errors.py`:

```python
class MailerError(Exception):
    """Base de todos los errores del Mail_Module. Mensajes libres de secretos."""

class MissingConfigError(MailerError):
    """Falta una o más variables de configuración requeridas.
    Nombra las variables ausentes por nombre; nunca incluye valores."""

class TokenError(MailerError):
    """Falla al obtener el Access_Token. Incluye status HTTP si aplica.
    Nunca incluye client_secret, tenant_id, client_id ni cuerpos crudos sensibles."""

class GraphError(MailerError):
    """Falla de transporte frente a Microsoft Graph (no 401/403, que se devuelven
    como GraphResponse). Nunca incluye el Access_Token."""
```

Principios de manejo de errores:
- **No exposición de secretos**: todo mensaje de error se construye con texto fijo + metadatos no sensibles (nombres de variables, status HTTP, correlation id). Nunca interpola `Secret_Value`.
- **401/403 son diagnóstico, no excepción de transporte**: `Graph_Client` devuelve `GraphResponse` con el status; el CLI/mailer traduce a mensajes legibles (auth / permisos).
- **Config ausente falla temprano**: `load_config` recolecta *todas* las variables faltantes y las nombra en un solo `MissingConfigError`.
- **Timeouts explícitos**: todas las llamadas `requests` usan `timeout` para no colgar indefinidamente.

## Dependencies

`requirements.txt` con versiones fijadas (mínimo):

```
requests==2.32.3
python-dotenv==1.0.1
```

Para pruebas (opcional, p.ej. `requirements-dev.txt`): `pytest`, `hypothesis`, `responses` (o `requests-mock`) para mockear transporte HTTP.

## Security & Content Safety

### Gestión de secretos
- Secretos solo por entorno/`.env` (cargado con `python-dotenv`).
- `.env` incluido en `.gitignore`; se versiona únicamente `.env.example` sin valores reales.
- `MailerConfig.__repr__` enmascara credenciales.
- Ningún `Secret_Value` (TENANT_ID, CLIENT_ID, CLIENT_SECRET, Access_Token) se escribe en logs ni en stdout/stderr, en ninguna ruta (éxito o error).

### Contenido del correo (anti-phishing)
El `Test_CLI` compone contenido inequívocamente de prueba técnica:
- **Asunto**: `"Prueba de integración Microsoft Graph"`.
- **Cuerpo**: declara explícitamente que es una validación automatizada de integración, por ejemplo: *"Este es un correo de prueba técnica generado automáticamente para validar la integración con Microsoft Graph. No requiere ninguna acción del destinatario."*
- Sin enlaces engañosos, sin solicitudes de credenciales, sin suplantación de marca ni urgencia artificial. El contenido no imita, simula ni induce a engaño de tipo phishing.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Solicitud sendMail bien formada

*For any* subject, body y destinatario válidos, la solicitud construida por el `Graph_Client` SHALL usar el método `POST` contra `/v1.0/users/{Sender_Mailbox}/sendMail` (con el `Sender_Mailbox` configurado en la ruta), incluir el header `Authorization: Bearer {Access_Token}`, y producir un payload sin `ccRecipients`, `bccRecipients` ni `attachments`.

**Validates: Requirements 1.2, 1.3, 1.4, 2.3**

### Property 2: Solicitud de token bien formada

*For any* configuración válida, la solicitud construida por el `Token_Client` SHALL dirigirse al endpoint de token del tenant configurado, usar `grant_type=client_credentials`, incluir `scope=https://graph.microsoft.com/.default`, y presentar `client_id` y `client_secret` en el cuerpo de la solicitud.

**Validates: Requirements 2.1**

### Property 3: Configuración cargada desde el entorno

*For any* mapping de entorno que contenga todas las variables requeridas, `load_config` SHALL producir una `MailerConfig` cuyos campos coincidan exactamente con los valores provistos en ese mapping.

**Validates: Requirements 3.1**

### Property 4: Variable de configuración ausente es reportada por nombre

*For any* subconjunto no vacío de variables requeridas que se omita del entorno, `load_config` SHALL lanzar un `MissingConfigError` que nombre cada variable ausente y que no contenga el valor de ningún `Secret_Value`.

**Validates: Requirements 3.4**

### Property 5: Ningún secreto aparece en la salida ni en los errores del módulo

*For any* conjunto de `Secret_Value` (TENANT_ID, CLIENT_ID, CLIENT_SECRET, Access_Token) y *for any* resultado de las llamadas HTTP (éxito o fallo), ningún `Secret_Value` SHALL aparecer en los logs, en la salida ni en los mensajes de error emitidos por el `Mail_Module`.

**Validates: Requirements 2.4, 3.2**

### Property 6: Ningún secreto aparece en la salida del CLI

*For any* conjunto de `Secret_Value` y *for any* ruta de ejecución del `Test_CLI` (éxito, 401, 403), ningún `Secret_Value` SHALL aparecer en stdout, stderr ni en los logs del `Test_CLI`.

**Validates: Requirements 3.3**

### Property 7: El CLI muestra status HTTP y Correlation_Id

*For any* respuesta de `sendMail` con un status HTTP y un `Correlation_Id` dados, la salida del `Test_CLI` SHALL incluir tanto ese código de estado HTTP como ese `Correlation_Id`.

**Validates: Requirements 4.3**

## Testing Strategy

Enfoque dual: pruebas unitarias/example para escenarios concretos y edge cases, y property-based tests (mínimo 100 iteraciones) para propiedades universales. Todo el transporte HTTP se mockea (p.ej. `responses`/`requests-mock`) para aislar la lógica del I/O externo.

### Property tests
Cada property test referencia su propiedad del diseño con el formato: **Feature: graph-test-email, Property {number}: {property_text}**.

- **Property 1** — Generar subject/body/to aleatorios; con transporte mockeado, capturar la solicitud y aserciones sobre método, ruta (sender en path), header Bearer y ausencia de cc/bcc/adjuntos.
- **Property 2** — Generar configuraciones aleatorias; capturar la solicitud de token y verificar endpoint/tenant, grant_type, scope y presencia de credenciales.
- **Property 3** — Generar mappings de entorno aleatorios; cargar config y comparar campos.
- **Property 4** — Generar subconjuntos aleatorios de variables omitidas; verificar que el error nombra cada ausente y no contiene valores secretos.
- **Property 5** — Generar secretos aleatorios; ejecutar operaciones del módulo (éxito y fallo mockeados) capturando logs/salida; aserción de no-aparición de ningún secreto.
- **Property 6** — Generar secretos aleatorios; ejecutar el CLI en rutas éxito/401/403; aserción de no-aparición de secretos en stdout/stderr/logs.
- **Property 7** — Generar status y correlation ids aleatorios en respuestas mockeadas; verificar que ambos aparecen en la salida del CLI.

### Example / edge-case tests
- `send_mail` retorna `SendResult(success=True)` ante HTTP 202 (Req 1.5).
- CLI lee config e invoca `send_mail` una vez (Req 4.1).
- CLI muestra diagnóstico de token obtenido en éxito (Req 4.2).
- CLI muestra mensaje de autenticación en 401 (Req 4.4) y de permisos en 403 (Req 4.5).
- Contenido de prueba: asunto de integración técnica (Req 5.1), cuerpo de validación automatizada (Req 5.2), sin elementos de phishing (Req 5.3) — complementado con revisión manual.

### Smoke / static checks
- `send_mail` existe y es invocable con la firma `(subject, body, to)` (Req 1.1).
- No se importan `azure-identity` ni `msgraph-sdk` (Req 2.2).
- `.gitignore` contiene `.env` (Req 3.5).
- `requirements.txt` existe con todas las dependencias fijadas (Req 6.1) e incluye `requests` y `python-dotenv` fijados (Req 6.2).
