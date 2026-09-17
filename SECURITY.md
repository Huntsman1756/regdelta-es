# Seguridad y tratamiento de datos

## Superficie real

RegDelta es una CLI/biblioteca local Python con SQLite y blobs en disco. No
incluye servidor web, UI, autenticación de usuarios ni aislamiento multiusuario.
No exponerlo como servicio suponiendo que dispone de esas protecciones.
`watch` solicita fuentes oficiales BOE/BdE y almacena respuestas/provenance.
No hay LLM ni credenciales de proveedor de IA en el runtime del producto.

Los documentos de origen, metadatos, rutas y mensajes de error pueden contener
datos que no deben difundirse indiscriminadamente. Un documento público no
convierte toda la configuración local, logs o DB en material publicable.

## Credenciales de herramientas de desarrollo

El `opencode.json` local, sin seguimiento Git en la auditoría, contenía claves
plaintext. Se sustituyeron únicamente los campos `apiKey` por:

- NaN Builders: `{env:NAN_BUILDERS_API_KEY}`.
- OpenRouter: `{env:OPENROUTER_API_KEY}`.

Esto elimina esos valores del archivo actual, **no revoca las claves ni elimina
copias previas o salidas de herramientas**. El propietario debe rotarlas,
configurar las variables por un canal seguro y salir/reiniciar opencode. No se
verificaron rotación, valores del entorno ni autenticación. No se confirmó una
filtración pública y no hubo escaneo exhaustivo del historial. Una variable
ausente se sustituye por cadena vacía según la documentación de opencode.

El archivo `opencode.json` fue eliminado posteriormente del árbol de trabajo;
las referencias anteriores describen su estado en la auditoría. Si se recrea,
restringir `permission` y el contexto accesible: sanitizar credenciales no
restringe acceso a archivos ni evita enviar contexto a proveedores externos.
No usar herramientas de IA con datos privados o sellados sin autorización y
controles de acceso. No pegar claves en ejemplos, incidencias, commits, logs
ni comandos registrados.

## Evidencia sellada e integridad

- No abrir semánticamente `*/holdout/*` fuera del protocolo autorizado.
- Comprobar destinos resueltos, no solo el nombre DEV de un manifest. G1/G2
  reutilizan rutas de holdouts históricos; el runner de tests ordinarios debe
  excluir gates y no constituye por sí solo un sandbox.
- Mantener entradas de evidencia solo lectura. Escribir resultados nuevos en
  ubicaciones autorizadas, nunca sobre informes/manifests/seals históricos.
- Los hashes detectan discrepancias; no proporcionan confidencialidad, permisos
  de acceso ni almacenamiento WORM. SQLite y blobs siguen siendo modificables
  por procesos con permisos suficientes.

Respaldar DB y raw de forma coherente y probar recuperación/verificación de
integridad. No asumir durabilidad universal frente a corte de energía por el
uso de `fsync` y reemplazo en `src/regdelta/rawstore.py:21–41`.

## Entradas y recursos

El HTTP del working tree auditado limita cuerpos a 128 MiB y usa timeout de
60 segundos con un reintento de errores de red (`src/regdelta/http.py:13–16`).
No extrapolar esas defensas a scripts históricos de captura: por ejemplo,
`scripts/g0c/probe_common.py:65–84` lee el cuerpo completo sin ese límite.
No ejecutar capturas como pruebas offline.

El PDF interno no es un parser general endurecido: su recorrido y descompresión
requieren revisión de límites (`src/regdelta/sources/boe_pdf.py:68–98`). Este es
un hallazgo estático de robustez, no un exploit ni una regresión reproducida.
Separar trabajos de parsing, limitar recursos y no abrir documentos arbitrarios
con privilegios o acceso a secretos.

## Verificación acotada

La suite completa local pasó tras revisión estática de seguridad: reutilizó
semánticamente evidencia G0-G/G1 ya abierta en DEV; el holdout G2 solo fue leído
para hashes por las guardas de sello. No hubo apertura semántica del holdout
actual G2 ni CNMV y el diff Git de evidencia quedó vacío. Esto no convierte
cualquier ejecución futura de scripts o replays en segura.

La carga de blobs de aplicabilidad ahora verifica SHA-256 y maneja `parse_error`
(`src/regdelta/applicability.py:114–132`), con seis tests sintéticos pasando.
Esto no resuelve los hallazgos semánticos de aplicabilidad/ownership de `AUDIT.md`.

`uvx pip-audit --path .venv/Lib/site-packages --progress-spinner off` informó
«No known vulnerabilities»; omitió el paquete local `regdelta`. Es un resultado
sobre dependencias instaladas y vulnerabilidades conocidas, no una auditoría
completa del código, licencias o historial de secretos.

Las reglas de ignore ahora cubren configuración local, secretos habituales y
outputs. No revocan claves ni eliminan datos previamente registrados. La CI en
`.github/workflows/checks.yml:8–39` usa permisos read-only, actions fijadas por
SHA, checkout sin credenciales persistidas y sparse checkout sin evidencia;
su ejecución alojada todavía no está verificada.

## Comunicación de problemas

No hay un canal privado de reporte ni una política de versiones soportadas
establecidos en este repositorio. El propietario debe definirlos; este documento
no inventa dirección, contacto ni plazo de respuesta.

Hasta entonces, no publicar credenciales, datos privados ni contenido sellado
en una incidencia pública. Preparar una descripción saneada con versión/commit,
componente, precondiciones y evidencia no sensible; acordar un canal privado
con el propietario antes de transmitir material confidencial. Los problemas
jurídicos/factuales también deben conservar la distinción entre incertidumbre,
fallo reproducido y hallazgo estático.
