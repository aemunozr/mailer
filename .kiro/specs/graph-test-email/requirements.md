# Requirements Document

## Introduction

Esta funcionalidad entrega una integración en Python para enviar correos de prueba técnica a través de Microsoft Graph API usando autenticación app-only (OAuth2 client credentials). El objetivo es validar de forma automatizada la conectividad y los permisos de una aplicación registrada en Entra ID con el permiso de aplicación `Mail.Send`, enviando correos desde un buzón de origen fijo (`phishing@itau.cl`).

El entregable se compone de dos partes: (a) un módulo limpio y reutilizable que expone una API `send_mail(subject, body, to)` con remitente fijo tomado de configuración, y (b) un script/CLI de prueba aislado que lee la configuración del entorno y produce diagnóstico detallado por paso.

La implementación usa `requests` directamente contra el endpoint de token OAuth2 y contra `POST /users/{mailbox}/sendMail`, sin depender de `azure-identity` ni `msgraph-sdk`. Todos los secretos se gestionan exclusivamente mediante variables de entorno o un archivo `.env` excluido de git.

Restricción crítica: el correo de prueba debe ser inequívocamente identificable como una prueba técnica de integración y no debe imitar, simular ni inducir a engaño de tipo phishing al destinatario.

## Glossary

- **Mail_Module**: Módulo Python reutilizable que expone la función `send_mail(subject, body, to)` y encapsula la obtención de token y el envío a Microsoft Graph.
- **Test_CLI**: Script de prueba aislado que lee la configuración del entorno e invoca al Mail_Module, mostrando diagnóstico por paso.
- **Config_Loader**: Componente del Mail_Module responsable de leer la configuración (TENANT_ID, CLIENT_ID, CLIENT_SECRET, buzón de origen, destinatario) desde variables de entorno o archivo `.env`.
- **Token_Client**: Componente del Mail_Module que solicita un token de acceso OAuth2 al endpoint de token de Entra ID mediante el flujo client credentials.
- **Graph_Client**: Componente del Mail_Module que envía el correo mediante `POST /users/{mailbox}/sendMail` de Microsoft Graph usando el token de acceso.
- **Sender_Mailbox**: Buzón de origen fijo definido en configuración (`phishing@itau.cl`) desde el cual se envían los correos.
- **Client_Credentials_Flow**: Flujo OAuth2 app-only en el que la aplicación se autentica con CLIENT_ID y CLIENT_SECRET para obtener un token sin usuario interactivo.
- **Access_Token**: Token de acceso OAuth2 emitido por Entra ID y usado como credencial Bearer frente a Microsoft Graph.
- **Correlation_Id**: Identificador de correlación (`request-id`/`client-request-id`) devuelto por Microsoft Graph, usado para diagnóstico.
- **Env_File**: Archivo `.env` que contiene secretos de configuración y que debe estar excluido del control de versiones.
- **Secret_Value**: Cualquier valor sensible de configuración, incluyendo TENANT_ID, CLIENT_ID, CLIENT_SECRET y el Access_Token.

## Requirements

### Requirement 1

**User Story:** As a desarrollador de integración, I want un módulo reutilizable que exponga `send_mail(subject, body, to)`, so that pueda enviar correos vía Microsoft Graph desde otro código sin reimplementar la autenticación.

#### Acceptance Criteria

1. THE Mail_Module SHALL exponer una función pública `send_mail(subject, body, to)` que acepte asunto, cuerpo y destinatario como parámetros.
2. THE Mail_Module SHALL usar el Sender_Mailbox definido en configuración como remitente de cada correo enviado.
3. WHEN se invoca `send_mail(subject, body, to)`, THE Mail_Module SHALL enviar el correo mediante `POST /users/{Sender_Mailbox}/sendMail` de Microsoft Graph.
4. THE Mail_Module SHALL construir el envío sin campos CC, BCC ni archivos adjuntos.
5. WHEN se invoca `send_mail(subject, body, to)` y el envío se completa correctamente, THE Mail_Module SHALL retornar un resultado que indique éxito al llamador.

### Requirement 2

**User Story:** As a desarrollador de integración, I want autenticación app-only mediante client credentials, so that la aplicación pueda enviar correos sin un usuario interactivo.

#### Acceptance Criteria

1. WHEN el Mail_Module requiere un Access_Token, THE Token_Client SHALL solicitar el token al endpoint de token OAuth2 de Entra ID usando el Client_Credentials_Flow con TENANT_ID, CLIENT_ID y CLIENT_SECRET.
2. THE Token_Client SHALL usar la biblioteca `requests` para la solicitud HTTP al endpoint de token, sin usar `azure-identity` ni `msgraph-sdk`.
3. WHEN el Token_Client recibe un Access_Token válido, THE Graph_Client SHALL incluir el Access_Token como credencial Bearer en la solicitud a Microsoft Graph.
4. IF la solicitud de token devuelve un error, THEN THE Token_Client SHALL retornar un error que identifique la falla de obtención de token sin exponer ningún Secret_Value.

### Requirement 3

**User Story:** As a responsable de seguridad, I want que los secretos se gestionen solo por entorno y nunca se registren, so that las credenciales no queden expuestas en el repositorio ni en los logs.

#### Acceptance Criteria

1. THE Config_Loader SHALL leer TENANT_ID, CLIENT_ID, CLIENT_SECRET, el Sender_Mailbox y el destinatario de prueba exclusivamente desde variables de entorno o desde el Env_File.
2. THE Mail_Module SHALL excluir cualquier Secret_Value de todos los mensajes de registro y de salida.
3. THE Test_CLI SHALL excluir cualquier Secret_Value de todos los mensajes de registro y de salida.
4. IF una variable de configuración requerida está ausente, THEN THE Config_Loader SHALL retornar un error que identifique la variable faltante por nombre sin exponer su valor.
5. THE codebase SHALL incluir el Env_File en la lista de exclusión de control de versiones.

### Requirement 4

**User Story:** As a ingeniero de QA, I want un CLI de prueba con diagnóstico por paso, so that pueda identificar rápidamente en qué etapa falla la integración.

#### Acceptance Criteria

1. WHEN se ejecuta el Test_CLI, THE Test_CLI SHALL leer la configuración desde el entorno mediante el Config_Loader e invocar `send_mail(subject, body, to)` del Mail_Module.
2. WHEN el Token_Client obtiene un Access_Token correctamente, THE Test_CLI SHALL mostrar un mensaje de diagnóstico que confirme la obtención del token sin exponer su valor.
3. WHEN el Graph_Client recibe la respuesta de `sendMail`, THE Test_CLI SHALL mostrar el código de estado HTTP y el Correlation_Id de la respuesta.
4. IF Microsoft Graph o el endpoint de token devuelve un estado HTTP 401, THEN THE Test_CLI SHALL mostrar un mensaje que indique falla de autenticación.
5. IF Microsoft Graph devuelve un estado HTTP 403, THEN THE Test_CLI SHALL mostrar un mensaje que indique falta de permisos de la aplicación.

### Requirement 5

**User Story:** As a destinatario del correo de prueba, I want que el mensaje sea claramente una prueba técnica, so that no sea confundido con un intento de phishing o engaño.

#### Acceptance Criteria

1. THE Test_CLI SHALL usar un asunto que identifique el mensaje como prueba de integración técnica, por ejemplo "Prueba de integración Microsoft Graph".
2. THE Test_CLI SHALL usar un cuerpo que indique explícitamente que el mensaje corresponde a una validación automatizada de integración.
3. THE Test_CLI SHALL componer el contenido del correo de prueba sin elementos que imiten, simulen o induzcan a engaño de tipo phishing al destinatario.

### Requirement 6

**User Story:** As a desarrollador que instala el proyecto, I want dependencias con versiones fijadas, so that la instalación sea reproducible.

#### Acceptance Criteria

1. THE codebase SHALL incluir un archivo `requirements.txt` que liste las dependencias del proyecto con versiones fijadas.
2. THE `requirements.txt` SHALL incluir `requests` y `python-dotenv` con versiones fijadas como dependencias mínimas.
