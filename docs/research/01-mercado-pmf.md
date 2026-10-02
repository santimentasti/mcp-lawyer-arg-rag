# Investigación de mercado / Product-Market Fit (2026-10-02)

> Muchas cifras provienen de snippets de buscador (los sitios argentinos bloquearon el fetch). `[snippet]` = no verificado en la fuente completa; `[incierto]` = no confirmado.

## 1. Tamaño de mercado
| Métrica | Dato | Fuente |
|---|---|---|
| Abogados en el país | ~126.000 (FACA, ~1 c/365 hab.) | derechoenzapatillas.com 2023 [snippet] |
| CPACF (CABA / justicia nacional) | 86.524 en padrón electoral abril 2026 | [Infobae 2026-04-19](https://www.infobae.com/judiciales/2026/04/19/elecciones-en-el-colegio-publico-de-la-abogacia-de-la-capital-federal-este-martes-y-miercoles-votan-cerca-de-90000-matriculados/) |
| Provincia de Buenos Aires | 57.190 (dato 2020, Caja de Abogados) | diariojudicial [snippet, viejo] |
| Solos / estudios chicos | Sin encuesta fiable. Juztina: ~40% de sus usuarios son independientes | abogados.com.ar |

Estimación de trabajo: **~130–150k matriculados** (hay doble matriculación); CABA+PBA es el mercado inicial. Sólo 13.660 votaron en CPACF 2024, así que hay muchos matriculados inactivos.

## 2. Competencia
**Editoriales (moat de contenido)**
- **Thomson Reuters La Ley**: lanzó *CoCounsel Core* en Argentina el 2025-12-16, localizado a derecho argentino.
- **elDial**: "Área IA" (sept. 2026), RAG sobre derecho argentino que redacta y audita escritos. Planes de ARS 34.500 a 124.500/mes [snippet].
- **Erreius** y **Microjuris**: venden con convenios de descuento con colegios (20–35%).
- **vLex / Vincent AI**; **SAIJ / InfoLEG** (gratis, datos abiertos).

**Startups IA**
- **Magnar** (Chile): US$8M Serie A, llegó a AR en 2026, ~US$600/mes por estudio.
- **Juztina** (Perú): US$10/mes.
- **JurisprudenciaARG**: 8.700+ abogados en un año.
- **RivoLegal**: ARS 49k–399k/mes.
- **Veredicta**: desde US$10/usuario.
- Gestión de causas: Lex-Doctor, Iurix, Legal Manager.

**MCPs argentinos open source ya existentes**: `saij-mcp` (hernan-cc), `juba-mcp`, `up-law-argleg-mcp` (UP Derecho), Legal-MCP-Server Argentina (Psflores), `mcp-abogadoenquilmes` (dice tener 285k+ fallos).
→ **La búsqueda de jurisprudencia/normativa pública ya es commodity.**

## 3. Análogos globales
- 2026-05-12: Anthropic lanzó "Claude for Legal": 20+ conectores MCP (CoCounsel, Harvey, iManage, CourtListener…) y 12 plugins por área de práctica.
- No se encontró ningún conector argentino o en español en los directorios oficiales [incierto].

## 4. Dolores del litigante
1. **Notificación electrónica + plazos**: en PJN el aviso por mail es mera cortesía; el plazo corre igual.
2. **Sistemas fragmentados**: PJN (Lex100), SCBA/MEV, EJE (CABA). Cada uno con sus propios feriados, ferias y asuetos.
3. **Calculadoras de plazos primitivas**: cuentan días, pero no entienden el acto procesal.
4. **Intereses / actualización**: tasas distintas por fuero y jurisdicción.
5. **Citas verificables**: ya hubo sanciones por fallos inventados por IA.
6. Redacción de escritos.

## 5. Disposición a pagar
Solo: ~US$10–50/mes; estudio: US$200–600/mes (lectura aproximada de los precios publicados).

## 6. Regulación y ética
- **Citas falsas sancionadas**: "Giacomino c/ Monserrat" (Rosario, 2025, apercibimiento y remisión al Colegio); Cámara Civil de Roca (26 fallos inexistentes); en 2026 se anuló una resolución judicial redactada con IA.
- **Guía IA del CPACF (jul. 2025)**: control humano, confidencialidad; citar jurisprudencia inexistente es falta ética.
- Jujuy Acordada 31/2025; la SCBA tiene en consulta un reglamento de IA (2026).
- **Ley 25.326** (transferencia internacional de datos, Disp. 60-E/2016) → minimizar datos de clientes.

## 7. Distribución
- **Directorio de apps de ChatGPT** (desde 2025-12-17): org verificada, cobro por checkout externo, OpenAI no cobra comisión.
- **Directorio de conectores de Claude** + patrón de plugins legales.
- **Convenios con colegios** (CPACF, colegios departamentales PBA, CASI), prensa especializada (Diario Judicial, abogados.com.ar, Microjuris).

## Síntesis
**Hipótesis de PMF**: el litigante civil/comercial solo o de estudio chico (CABA/PBA) ya usa ChatGPT/Claude pero no confía en ellos. Pagaría poco por un conector que (a) devuelve **sólo fuentes verificables y enlazadas** y (b) hace la **aritmética procesal** que los LLM generales hacen mal: etapa → próximo acto → plazo en días hábiles judiciales por jurisdicción.

**ICP**: abogado solo o estudio de 2–5, matriculado en CPACF o en un colegio de PBA. Daños, cobros, locaciones, consumo, en PJN y SCBA. Ya paga ChatGPT Plus o Claude Pro; no tiene La Ley.

**Wedge**: "Etapas + Plazos" (+ calculadora de intereses en v2) y un **verificador de citas**. La búsqueda de jurisprudencia queda como feature de apoyo, no como producto.

**Precio (hipótesis)**:
- Free: consultas al CCyCN/CPCCN + pocos plazos al mes.
- Pro: US$10–20/mes, indexado en ARS.
- Estudio: US$50–150/mes por 5 usuarios.
- Descuento por convenio con colegios.
- Cobro con Mercado Pago o Stripe.

**Riesgos**: commoditización; responsabilidad por plazos mal calculados; secreto profesional y datos personales; sin APIs públicas de PJN/MEV/EJE; dependencia de plataforma; fragmentación (24 códigos procesales).
