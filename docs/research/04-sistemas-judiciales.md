# "Recordar mi caso": integración con los sistemas judiciales (2026-10-02)

**Conclusión:** ningún poder judicial (PJN, CSJN, SCBA, CABA) publica una API oficial para terceros, y no existe una integración MCP oficial. Lo que existe usa una de dos vías:
- consulta pública por número de expediente (EJE CABA tiene una API JSON pública no documentada; la consulta pública PJN tiene captcha);
- **las credenciales del propio abogado** (todos los productos comerciales y OSS).

No se encontraron convenios formales con los tribunales. (Los sitios judiciales estaban bloqueados desde el entorno de investigación; lo marcado `(no verificado)` no se pudo confirmar.)

## Sistemas
| Sistema | ¿Consulta pública sin login? | Auth | ¿API? | Captcha | OSS |
|---|---|---|---|---|---|
| PJN consulta pública (scw.pjn.gov.ar / Lex100) | Sí, por fuero + número + año (penal/familia restringidos) | — | No | Sí (resolución humana) | legal-ar-mcp-hub (MIT, HITL) |
| PJN Portal / notificaciones | No | CUIT/CUIL + clave (SSO Keycloak), SAU | No pública; el backend `api.pjn.gov.ar/eventos` devuelve JSON | normalmente no | **monitor-judicial-ar (MIT)** |
| CSJN sjconsulta | Sí (fallos) | — | No | (no verificado) | legal-ar-mcp-hub |
| PBA MEV | **No** ("no tiene consulta anónima ni API JSON") | usuario + clave + departamento; las claves vencen | No (ASP + HTML) | no documentado | monitor-judicial-ar, legal-ar-mcp-hub |
| PBA Portal Notificaciones (Ac. 4013) | No | **certificado en token** (AC-SCBA) | No | — | ninguno: no automatizable desde un servidor |
| CABA EJE | **Sí**: `iol-api/api/public` (`/expedientes/lista`, `encabezado`, `ultimaAccion`, `actuaciones`, PDF); reservados → error 1004 | Keycloak CUIT + clave EJE, o miBA | JSON no documentado | sólo vía miBA | monitor-judicial-ar, legal-ar-mcp-hub |

**OSS de referencia**
- [Probanza-ar/monitor-judicial-ar](https://github.com/Probanza-ar/monitor-judicial-ar) (Node, MIT): PJN + EJE + MEV, PDFs, plazos/caducidad, mail diario. Corre local, con credenciales en `.env`.
- [legal-ar-mcp-hub](https://github.com/jacquelineocampo-creator/legal-ar-mcp-hub) (TS, MIT): prototipo con 15 fuentes y captcha resuelto por humanos.
- `lucasm86/expediente-scout` (Python, sin licencia): expediente PJN → markdown.

**Comerciales**
- RivoLegal y LexAlert sincronizan PJN/MEV con las credenciales del usuario.
- Iurix es el sistema *de los tribunales*, no del abogado.
- No se encontraron convenios.

## Restricciones
- **Credenciales**: la identidad electrónica judicial es personal y cada acto se atribuye al titular. Las credenciales no deben salir del control del abogado; centralizarlas en la nube es un punto único de falla. Leer los "eventos" PJN podría equivaler a notificarse → no hacerlo en silencio.
- **Ley 25.326**: los datos de causas incluyen datos sensibles (salud, penal, familia, menores). Implica registro de base, medidas de seguridad, confidencialidad y transferencia internacional (LLM en el exterior).
- **Secreto profesional**: el abogado responde por lo que sube a terceros (retención, borrado, no-entrenamiento).
- **Captchas**: muestran la intención de bloquear bots → nunca resolverlos automáticamente. Hacer polling moderado (1 vez/día) con caché.
- **"Autorizados"** en expedientes autorizan a *personas*, no a software. No hay OAuth para terceros.

## Arquitectura recomendada para "recordar mi caso"
1. **Memoria de expediente (sin acceso a tribunales)**: el abogado carga fuero, número/año, partes, juzgado y estado; o pega/sube el PDF o la notificación. Se guarda detrás de un handle (`expediente_id`, alineado con la spec MCP stateless) y requiere OAuth.
2. **Consulta pública server-side**: API pública de EJE CABA; link a la consulta PJN con captcha resuelto por humanos; caché + rate limit.
3. **Agente local opcional (companion)**: un proceso en la máquina del abogado, con credenciales en el keychain del sistema, sincroniza PJN eventos / MEV / EJE privado y sube **sólo un resumen normalizado** (clave, fecha, tipo, texto corto). Se puede adaptar de monitor-judicial-ar (MIT). Confirmación explícita ante cualquier acto que implique notificarse.
4. **Reenvío de mails de notificación** (PJN/SCBA): un filtro de Gmail → parser → actualiza el estado. No toca credenciales judiciales.
5. **Datos**: mínimos, cifrados, con retención y borrado, LLM en modo no-entrenamiento y DPA.

## Fases
- **0**: memoria manual + ingesta de PDF/texto.
- **1**: consultas públicas (EJE API, PJN con humano en el loop) + reenvío de mails.
- **2**: agente local opt-in (PJN eventos, MEV, EJE privado).
- **3**: pedir acceso formal o convenio a PJN / SCBA / Consejo de la Magistratura CABA, idealmente vía un colegio (CPACF, CASI), con dictamen legal previo sobre términos de uso y datos personales.

**Riesgos**: backends no documentados que cambian sin aviso; bloqueo de cuentas o claves vencidas; posible violación de términos; responsabilidad por plazos perdidos; exposición de datos sensibles.
