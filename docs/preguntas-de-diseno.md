# Preguntas de diseño abiertas

Respondidas (2026-10-02):
- **Usuario inicial**: abogado litigante solo o de estudio chico.
- **Datos de casos**: el MVP sólo maneja normativa pública; no guarda expedientes de clientes.
- **Jurisdicciones**: Nación + CABA (mismo modelo: CPCCN) + Provincia de Buenos Aires.
- **Stack**: Python + FastMCP.

## Producto / negocio
1. **Wedge.** La investigación de mercado muestra que la búsqueda de normas y fallos ya es commodity: hay varios MCP argentinos gratis, más elDial IA y CoCounsel. Lo diferencial es **"etapas + plazos + verificador de citas"**. ¿Lo validamos así, o tenés evidencia (clientes, colegas) de otro dolor?
2. **¿Quién paga?** ¿El abogado individual (US$10–20/mes), el estudio (por usuario) o un convenio con colegios (CPACF, colegios departamentales de PBA, CASI) con descuento a matriculados?
3. **Canal.** ¿Tenés acceso a algún colegio, cátedra o grupo de abogados para un piloto de 10–20 usuarios?
4. **Cobro.** El directorio de ChatGPT no cobra comisión, pero el cobro es externo (Mercado Pago/Stripe) y requiere cuenta/login. ¿Free-tier sin login + Pro con OAuth?
5. **Responsabilidad.** Un plazo mal calculado es el riesgo número uno. ¿Querés un abogado revisor de los datos procesales (rol "editor jurídico")? ¿Términos y condiciones con descargo de responsabilidad?
6. **Marca y dominio.** ¿Nombre del producto? (El código usa `lexar` como placeholder.) La verificación en el directorio de OpenAI exige un dominio propio.

## Alcance jurídico
7. **¿Qué fueros y procesos primero?** Hoy: ordinario, sumarísimo, ejecutivo, ejecución de sentencia, cautelares, BLSG, diligencias preliminares, prueba anticipada, desalojo, interdictos, división de condominio, sucesiones, concurso y quiebra. ¿Agregamos **familia** (CCyCN Libro II, mucho volumen) o **consumo** (Ley 24.240, fuero de consumo CABA)?
8. **Jurisprudencia.** ¿La integramos en v1 (SAIJ, CSJN, dataset HF de SAIJ) o la dejamos fuera para diferenciarnos con exactitud normativa?
9. **Intereses y actualización.** Calculadora de tasas (BNA activa/pasiva, actas CNCiv, SCBA). Es la otra gran aritmética donde fallan los LLM. ¿Entra en el MVP?
10. **PBA.** ¿Tenés acceso al texto consolidado del CPCC PBA (normas.gba.gob.ar) o preferís que lo scrapee?

## Técnico
11. **"No perder contexto".** ¿Te referís a (a) que la base se actualice con normas nuevas sin perder versiones (resuelto: versionado temporal), (b) que el conector recuerde el expediente entre conversaciones (requiere guardar datos de clientes, hoy fuera del MVP), o (c) ambas?
12. **¿Embeddings ya?** Hoy la búsqueda es BM25 (rápida y exacta). Pasar a híbrida (bge-m3 + pgvector) mejora las consultas en lenguaje coloquial ("me chocaron el auto"). ¿Priorizamos eso o el CPCC PBA?
13. **¿Dónde corre el sandbox?** Recomiendo Railway (≈US$5/mes) + túnel local para desarrollo. ¿Tenés cuenta o preferís otra plataforma?
14. **Graphiti / grafo.** Recomiendo postergarlo hasta tener jurisprudencia (el grafo rinde cuando relaciona normas ↔ fallos ↔ conceptos). ¿De acuerdo?
15. **Autenticación.** Sin login para normativa pública. Si más adelante se guardan expedientes: OAuth 2.1 + PKCE con CIMD (spec MCP 2026-07) vía un IdP (WorkOS/Auth0/Stytch). ¿Algún proveedor preferido?
16. **Apps SDK UI.** ChatGPT permite widgets (p.ej. una línea de tiempo del expediente o un calendario de vencimientos). ¿Lo querés para la demo?
