> Especificación de trabajo de la V1, generada por un panel de tres diseños y un juez a partir de la lista de funciones del producto. En inglés porque es el documento que siguen los agentes que construyen; el resumen en castellano está en [diseno-v1.md](../diseno-v1.md).

# V1 core design review and recommended synthesis

**Bottom line.** D2 and D3 tie at 41/50 and D1 scores 39. None of them is right on its own. The recommended core uses D1's typed SQLite schema, D2's control layer (pure rule engine, IBAN registry, sticky findings, priority floors) and D3's build path: fix the existing defects first, migrate with zero API calls, run today's rules on corrected data through an adapter, and set the cache policy before the schema bump. Sections 3 to 12 specify it.

---

## 1. What I checked before scoring

**Repo state**
- Python 3.11.17 and SQLite 3.45.1. pydantic, pytest and anthropic are not installed in this container.
- There are 125 test functions. The README and fase-0 doc still say 64.

**Defects the designs cite. All confirmed:**
- `dashboard.py:98,111` and `facturacion.py:145,277` use `startswith("uur")`. Lines whose unit is "uren" are dropped from the hours, the projection and the simulator (found by D3).
- `parsing.py:24` `_CURRENCY` silently strips `$`, `£` and `USD`, so a USD invoice parses as EUR (D2).
- `dashboard.py:476-517` `detectar_ibanes` makes the oldest document IBAN the "habitual" one. A fraudulent first invoice becomes the reference (D2).
- `dashboard.py:390` emits B4 as `critico`, but the catalogue says Retención (D2).
- `serve.py:198-203` POST `/api/ejecutar` checks neither Origin nor a token. Any web page can start paid runs with a form POST (D2, D3). GET `/api/datos` never checks Host, so DNS rebinding can read it (D3).
- `extract.py:55` always writes `out/<sha12>.json`, and `cache.matches` is strict. Any change of model, prompt or schema version re-pays every document on the next `extract` and overwrites the v1 evidence (D3).

**Defects none of the three found:**
- `serve.py:169` `_cors` checks `origen.startswith(("http://localhost","http://127.0.0.1"))`. I tested it: `http://localhost.attacker.example` and `http://127.0.0.1.nip.io` pass. The server reflects them in `Access-Control-Allow-Origin`, so a page on such a host can read `/api/datos`, full IBANs included. The fix is an exact match on scheme, host and port.
- `checks.check_vat_amount` reports KOR-with-VAT as `E4`. The catalogue rule for that case is E3.
- `detectar_cambios_de_tarifa` groups by the printed `supplier_name`, not by `_identidad`. A provider who changes its printed name escapes G3, and two providers with the same name are merged.
- The code's D2 (sum of lines equals the base) and D2b (quantity times rate) do not match the catalogue's D2 (units times rate equals subtotal). Keep the code IDs and fix the doc.
- `_propagar_alertas_a_filas` joins alerts to rows by file name. Two different PDFs with the same name from two folders collide.

**D1's database guard works as described.** On 3.45.1:
- an UPDATE without a matching `cambio_campo` row aborts, and an audited one passes;
- `CHECK (date(x) IS x)` rejects `2026-02-30`;
- STRICT rejects `'12.50'` in an INTEGER column;
- `strftime('%V')` returns NULL, so ISO weeks have to be computed in Python.

**Claude API facts** (from the bundled reference, cached 2026-10-06):

| Fact | Detail |
|---|---|
| Prices per MTok | claude-opus-5: $5 in / $25 out. claude-opus-5-5: $4 / $20. `pricing.py` has no row for claude-opus-5-5. |
| Batches | 50% of the price, and they accept `output_config.format` json_schema. They reject the server-side `fallbacks` parameter. |
| Schema rules | Every object needs `additionalProperties:false`. Recursion, min/max and length constraints are not supported. A new schema compiles once and is then cached for 24 h. |
| Caching | Minimum cacheable prefix on Opus 5 and 5.5 is 512 tokens. |
| Token counting | `count_tokens` accepts structured outputs. |
| Sync call | `messages.parse(output_format=Model)` is still the documented usage. |
| Opus 5.5 | Thinking can't be disabled, and effort defaults to `medium`. |

---

## 2. Scores

| Criterion | D1 data-model-first | D2 risk-and-control-first | D3 incremental |
|---|---|---|---|
| Coverage of the feature list | 9 | 9 | 8 |
| Money controls: correct and safe | 8 | 9 | 7 |
| Fit with the code and the security architecture | 7 | 8 | 9 |
| Implementable now, without the unknown formats | 7 | 6 | 9 |
| Testability | 8 | 9 | 8 |
| **Total (out of 50)** | **39** | **41** | **41** |

**D1 (data model first)**
- **Coverage 9.** Every item in §1–21 has an explicit table, view or rule. That includes the split between invoice lines and allocations, billing cycles, the 7 provenance sources and the 11 permissions.
- **Money 8.** Strengths:
  - the database itself refuses an update without an audit row;
  - the bank registry is insert-only;
  - triggers allow only humans to verify an IBAN, mark an invoice reviewed or record a BTW filing;
  - finding fingerprints include the compared values;
  - the F rules cannot be overridden, and a master-data IBAN change (F6) blocks.

  Missing: a statement continuity check, double-payment detection, source freshness and sticky rule families. A manual priority set on an exception can lower a Blocked case.
- **Fit 7.** It reuses the checks and detectors and keeps the JSON contract. But it misses every existing defect listed above, and it keeps the strict cache that causes the re-pay trap.
- **Implementability 7.** Rules return `sin_datos` while a source is missing. But the first migration (0001) creates the whole schema, including planning and bank tables designed before their formats are known.
- **Testability 8.** In-memory fixture, trigger tests, a parity test against `test_dashboard`, table-driven priority tests. The rules query the database directly, which makes them harder to test in isolation.

**D2 (risk and controls first)**
- **Coverage 9.** All sections, plus extra controls. The Object overview is the thinnest part.
- **Money 9.** The strongest set:
  - a registry of verified IBANs;
  - the callback must go to the master phone number that existed before the document arrived, with a cool-down after a phone change;
  - separation of duties;
  - sticky rule families;
  - K4 double-debit and K6 statement-continuity checks;
  - source freshness;
  - all-or-nothing loading for imports that set money states;
  - a policy loader that refuses to relax the hard rules;
  - clean invoices are labelled "sin objeciones del sistema", never "aprobada".

  Flaws:
  - partial payments are not represented, so cash flow is overstated;
  - SOD2 would deadlock a one-person administration;
  - a 36 h freshness limit plus all-or-nothing master imports can hold every invoice after a weekend or one bad row.
- **Fit 8.** It found 4 real defects and maps every rule in arquitectura.md. But its EAV store (`valor_campo`) departs from the dict-based code. And CLI-only human actions don't suit an administration of one non-developer.
- **Implementability 6.** The largest scope: about 70 rules, separation of duties, a policy gate, EAV plus rebuilt projections, and nothing payable until a bulk IBAN attestation is signed.
- **Testability 9.**
  - Pure rules, enforced by an AST test and a recording proxy.
  - Results stay identical when the input is shuffled, and rebuilt projections must match the incremental ones.
  - An injected clock, a performance budget and an end-to-end injection test.

**D3 (incremental from the current code)**
- **Coverage 8.** Every check is mapped. But the store holds little typed state: the VAT breakdown, payment-time statistics and expected in/out per Object exist only in Python views.
- **Money 7.** Strengths: a property test proves no code path leads from a document to the bank registry, automatic payment matching needs an exact match, and findings carry value fingerprints.

  Gaps:
  - an IBAN that arrives through an Exact import becomes the F2/F3 reference and the exception closes itself, so master-data tampering is not caught;
  - no sticky families;
  - no continuity or freshness checks;
  - full credit notes are confirmed automatically.
- **Fit 9.** The only design that checked the code line by line: a golden snapshot, `/api/datos` kept byte-identical, an adapter that runs today's rules on corrected data, the cache trap, DNS rebinding, the missing dependencies.
- **Implementability 9.** Every step has a gate. The zero-API migration comes first and the one paid step is isolated. Unknown formats sit behind canonical models and YAML mappings.
- **Testability 8.** Concrete gates per step, a contract test per mapping, property and scope suites, and a fake client that counts API calls. Rule purity is not enforced structurally, and the identity tables are not protected by triggers.

---

## 3. Where the designs disagree, and what I pick

**1. Where current values live.**
- D1: typed tables, plus a provenance row per field, plus an append-only change log, enforced by triggers.
- D2: every value is an append-only assertion (`valor_campo`). Typed state exists only in projections that are rebuilt.
- D3: the extraction payload is read directly as the base layer, overrides are assertions, and everything is resolved in Python on each read.

**Pick D1, with D2's rules for values and D3's adapter.** From D2: a manual value outranks an automatic one, the original is never overwritten, and undo is a new change. From D3: an adapter rebuilds today's record dicts from the current values. *Why:* §3–8 and §17–18 are sums and filters over current values. Typed columns give SQL, indexes, CHECK constraints and a clean source for the portal projection. The guard trigger (verified above) makes "no change without an audit row" a database property. The adapter lets `checks.py`, `dashboard.py` and `facturacion.py` run unchanged on corrected data.

**2. How money is stored.**
- D1: integers (cents, thousandths of an hour, basis points).
- D2 and D3: TEXT decimals, summed in Python.

**Pick integers, and store unit rates in ten-thousandths of a euro (`_e4`).** That removes the precision loss D1 itself flags. The printed literal is always kept. *Why:* SUM, ORDER BY and filters stay exact in SQL. TEXT amounts compare as strings ('100.00' < '20.00'), and SUM() goes through floating point. Both break filters such as "amount ≥ 10.000" in §16 and §18.

**3. Which bank account counts as trusted.**
- D1: IBANs from the master data count as registered. A later change in the master data blocks (F6).
- D2: an independent registry. An Exact IBAN without a human verification blocks until someone signs a bulk attestation. An account is payable only if it is verified and present in Exact.
- D3: the Exact IBAN is the reference (left as an open question). An IBAN planted in Exact passes F2/F3, and the exception closes itself.

**Pick:**
- The first master import is the **baseline**, state "heredada". It is accepted as the reference, shown as unverified, and creates one attestation task at Attention level.
- Anything added, changed or removed in a later master import blocks (F5) until it is verified by callback.
- **Payable** means verified, attested or heredada, **and** present in the latest accepted Exact batch.
- D2's stricter behaviour stays available as a policy switch.

*Why:* this blocks both real attack paths (the document, and later tampering with the master data) while keeping day one usable. It closes D3's gap and matches rule 1 of arquitectura.md.

**4. The callback phone number.** Only D2 constrains it. The number called must be the master phone that existed before the triggering document arrived, and a phone change starts a cool-down. D2 and D3 never extract phone numbers from documents. **Pick D2**, with the cool-down configurable (default 14 days).

**5. Partial payments.**
- D1: records the real amounts, shows the remaining balance and raises a warning.
- D2: payment links carry no amount. Anything other than an exact match raises K2, and the invoice stays at its full amount.
- D3: full amount only.

**Pick D1 plus K2.** Store the real amounts. An invoice is Paid only when the balance is within tolerance (default 0,00). Otherwise it stays Outstanding or Overdue with the remaining balance, and K2 fires. There are no instalment plans and no partial-payment workflow. *Why:* the §7 figures "actual received" and "expected incoming" must match the money that actually moved.

**6. Partial versus all-or-nothing imports.** D2 loads every import all-or-nothing. D1 and D3 reject bad rows one by one. **Pick per source.** All-or-nothing for bank statements, planning snapshots, bank accounts, invoices and payments, where a half-loaded file creates false "unpaid" or "unbilled" states. Row by row for other master data, with the rejected rows reported as finding Z2.

**7. Source freshness.** Only D2 has it (36 h for Exact and TRNSPRNT, 96 h for the bank, after which rules hold). **Pick the mechanism, with defaults that suit manual exports:** bank 3 working days, Exact 7 days, TRNSPRNT 7 days. A stale source shows a banner and finding Z1, and the rules that depend on it return `sin_datos`, never ok. *Why:* a 36 h limit would hold every invoice every Monday in a one-person office.

**8. Planning storage.** D1 keeps one mirror table that is updated in place, plus a history trigger. D2 and D3 keep each import as an immutable snapshot batch. **Pick snapshots.** This follows rule 9 of arquitectura.md, every finding can cite its batch, and "planning changed after billing" becomes a diff between two batches.

**9. The rule engine.** D1's rules query the database. D2's rules are pure functions over a frozen snapshot, enforced by tests. D3 runs the existing functions over a resolved snapshot. **Pick D2**, with D3's adapter for the rules ported from today's code.

**10. A finding's identity versus its evidence.** D1 and D3 put the compared values into the identity, so new values mean a new finding (in D3, even a new exception). D2 keeps the identity (`clave`: rule plus target) separate from the evidence (`huella`: the compared values). **Pick D2.** An override stays tied to the evidence it accepted, so it cannot hide a new problem. Ownership and history do not split every time an amount changes.

**11. Closing findings automatically.** D1 marks a vanished finding "desaparecido" and D3 closes it as "resuelto_por_sistema". D2 has sticky families that never close themselves. **Pick D2's sticky list:** IBAN, duplicates, payment anomalies, VAT regime change, PO overrun, R2 and R3. Other rules close automatically, with the edit or import that caused it recorded. *Why:* "editing your way out of a warning" and master-data tampering are exactly the cases where the condition disappears but the problem is not solved.

**12. Overrides.** D1: the F rules cannot be overridden. D2: an explicit list that cannot be overridden, plus a second signer for blocking rules or amounts of 10.000 or more. D3: any finding can be overridden with permission and a reason. **Pick D2's list:** the F family, X1, D2/D3/D4/D6 on incoming invoices, E3/E4, K2/K4/K6, R2/R3. B2 is closed by merging or linking the invoices. A second signer is required when a second person holds the permission; otherwise the override is flagged `autoaprobada`.

**13. Separation of duties.** D2 enforces predicates SOD1–SOD5. D1 and D3 only record who did what, with optional four-eyes review. **Pick D2's predicates under a "si_hay_dos" policy:** enforced when two people hold the permission, otherwise allowed but flagged `autorrevisado`. That includes SOD2, which D2 keeps hard and which would deadlock one person.

**14. What one exception covers.** D1: one per affected entity, grouping its findings. D2: one per rule and entity. D3: one per fingerprint. **Pick D1, with each finding keeping its own lifecycle.** One owner and one follow-up date per invoice matches how the work is done: one email to the provider covers all its issues.

**15. When a review goes stale.** D1: the review is older than the latest non-calculated change. D2 and D3: a fingerprint of the current values plus the evidence of open findings. **Pick the fingerprint.** It also catches changes that arrive through master data or planning.

**16. Priority.** D1 and D3 use a ladder of rules. D2 uses minimum levels (floors) plus versioned points. **Pick D2's two layers with a trimmed points table.** Priority can only be raised by hand. D1 allowed an exception's priority to be set manually, which could lower a Blocked IBAN case.

**17. Human edits through the local server.** D1: POST with a CSRF token, an Origin check and a custom header. D2: no write endpoints until real authentication exists, so CLI only. D3: POST `/api/v2/acciones` with a token, after Host, Origin and token hardening. **Pick D3 (and D1), but only after the step-0 hardening, still bound to 127.0.0.1.** *Why:* §10 and §11 are daily work for a non-developer, so CLI only is not usable. Anyone able to get around local tokens already has the SQLite file. Entra ID comes with deployment.

**18. Cache and re-extraction.**
- D1: keeps the strict cache (database first, then out/).
- D2: accepts paying again after running `coste --estimar`.
- D3:
  - reusing any stored extraction of the same bytes (CONSERVAR) is the default, with `--estricta` for measurements;
  - re-extraction is a separate command with a budget;
  - a new extraction becomes current only after the score gate;
  - nothing is ever overwritten.

**Pick D3.** As verified above, the bump to schema v2 would otherwise silently pay for the whole folder again and destroy the v1 evidence.

**19. PO numbers in the extraction.** D1 and D2: the model fills `po_numbers`, only when the number is labelled as a PO. D3: the model copies every printed reference with its literal label, and code decides which one is a PO by matching it against the PO list. **Pick D3:** the model transcribes, code decides.

**20. Relationships proposed by the extraction.** D3 confirms a full credit note on an incoming invoice automatically. D1 and D2 treat every extracted relationship as a proposal. **Pick proposals only.** There are tens per month, and a wrong link silently marks an invoice Credited and changes VAT.

**21. Outgoing PDFs.** D1 and D2 use a separate prompt version. D3 uses one direction-neutral prompt and lets the intake route set the direction. **Pick D3:** only one prompt version has to be scored, and the direction never comes from the model.

**22. Unbilled and planned work in cash flow.** D1 adds its value to the expected amounts per Object. D2 and D3 show it on a separate line marked "estimado". **Pick the separate line.**

**23. IBAN masking.** D2 masks IBANs for users without a `ver_iban_completo` permission. The design brief (§8.3) says the internal panel shows the full IBAN. **Pick:** full IBAN in the internal console, masked only in the portal projection, as portal-consulta.md says.

**24. File location and IDs.** D1 uses `data/` with INTEGER IDs, D2 `datos/` with UUIDs, D3 `datos/` with deterministic hashes. **Pick `datos/`, INTEGER IDs and UNIQUE natural keys.** Re-running an import is safe because of the natural keys, so IDs don't need to be reproducible.

---

## 4. Conventions

- **Files.**
  - Database: `datos/bms.sqlite3` (environment variable `BMS_DB`); `/datos/` goes in .gitignore.
  - Original documents: a write-once content-addressed store at `datos/documentos/<sha[:2]>/<sha256>.<ext>`. Files are read-only (mode 0444), and `db verificar` re-hashes them.
- **Engine.**
  - Python's standard sqlite3. Refuse to run on SQLite older than 3.37.
  - Settings: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`.
  - Each command or import is one `BEGIN IMMEDIATE` transaction. It contains the data change, its `cambio_campo` rows, the `evento` row and the full recompute.
  - The SQL stays portable to Postgres (arquitectura.md §11).
- **Tables** are STRICT with an `INTEGER PRIMARY KEY`. Natural keys are UNIQUE: sha256, (fuente, id_externo), huella, clave.
- **Money and quantities** are integers. A lint test checks that no REAL column exists.

  | Suffix | Meaning |
  |---|---|
  | `_cent` | Euro cents, signed (credit notes are negative) |
  | `_mil` | Thousandths (hours, quantities) |
  | `_e4` | Ten-thousandths of a euro (unit rates) |
  | `_pb` | Basis points (VAT rates) |

  There is no currency column. A non-EUR document keeps NULL amounts and raises X1. `almacen/unidades.py` is the only converter. It raises on precision loss, leaving the value NULL with finding Q2, and never rounds silently.
- **Dates** are TEXT `YYYY-MM-DD` with `CHECK (x IS NULL OR date(x) IS x)`. Timestamps are UTC ISO-8601. `semana_iso` is computed in Python and stored.
- **`*_doc` columns** hold untrusted text from third-party documents. It is rendered with `textContent`, neutralised against formulas in CSV exports, and never interpreted.
- **Table classes.**
  - **TRACKED:** has a `rev` column. A BEFORE UPDATE trigger requires `NEW.rev = OLD.rev + 1` and a matching `cambio_campo(tabla, fila_id, rev)` row. BEFORE DELETE aborts; rows are retired, not deleted. Caches live in separate tables so the guard covers the whole row.
  - **APPEND-ONLY / IMMUTABLE:** BEFORE UPDATE and BEFORE DELETE abort.
  - **CACHE:** can be rebuilt at any time and is never the source of truth.
- **Migrations:** one numbered SQL file per build step. Its sha256 is recorded, and an applied file is never edited.

---

## 5. Tables

**A. Infrastructure, access, audit**

1. **`migracion`** (version, nombre, sha256, aplicada_en).
2. **`politica_version`** (sha256, fichero, contenido, vigente_desde, cargada_en, cargada_por). APPEND-ONLY. One row for every configuration file as applied: reglas, prioridad, btw, empresa, mappings.
3. **`usuario`** (id, nombre, email UQ, es_sistema, activo, token_sha256, creado_en). Seeded system users: sistema, extractor, importador, motor.
4. **`rol`**, **`rol_permiso`** and **`usuario_rol`** (with desde and hasta).
   - Permissions: the §19 eleven (`ver_facturas`, `editar_extraccion`, `anadir_informacion`, `cambiar_objeto`, `cambiar_po`, `marcar_pagada`, `anular_acreditar`, `resolver_aviso`, `anular_aviso`, `confirmar_iban`, `admin`) plus three proposed ones: `revisar_factura`, `gestionar_btw`, `importar_datos`.
   - A trigger prevents system users from holding roles.
5. **`evento`** (id, en, usuario_id, actor, tipo, resultado ok/denegado/error, tabla, fila_id, factura_id, motivo, datos_json, peticion_id UQ, hash_anterior, hash UQ). APPEND-ONLY, except one update that seals the hash. Denied attempts and document openings are logged too.
6. **`cambio_campo`** (id, evento_id, tabla, fila_id, factura_id, campo, rev, valor_anterior, valor_nuevo, fuente_anterior, fuente_nueva, motivo). A CHECK requires a reason for `manual_correccion`. APPEND-ONLY. This is the change history.

**B. Evidence (IMMUTABLE)**

7. **`documento`** (id, sha256 UQ, nombre_original, tipo_mime, bytes, ruta_cas, origen, ruta_declarada, mensaje_id, recibido_en, recibido_fuente, registrado_en, registrado_por).
   - `ruta_cas` is NULL when the original was not found (finding Q4).
   - `origen`: carpeta, correo, exact, trnsprnt, banco, manual or out_v1.
   - `ruta_declarada` is entrante, saliente, maestro, banco or planning. The intake route sets it, never the model.
   - `recibido_fuente`: correo, ingesta, mtime or desconocido.
8. **`extraccion`** (id, documento_id, modelo, prompt_version, schema_version, via api/lote/out_v1, extraido_en, request_id, uso_json, contenido_json, contenido_sha256; UQ on the document, model, both versions and the content hash). A document can have many extractions, and none is overwritten.
9. **`importacion`** (id, fuente, tipo, formato, documento_id, fichero_sha256, mapeo_sha256, exportado_en, cubre_desde, cubre_hasta, completa, estado, row counts, rechazos_json, iniciada_por, actor; UQ on fuente, tipo and file sha).
   - `estado`: en_curso, aceptada, rechazada or parcial.
   - Updates are allowed only while `en_curso`.
10. **`extracto_bancario`** (id, importacion_id, cuenta_propia_iban, secuencia, saldo_inicial_cent, saldo_final_cent, desde, hasta, con_saldos). Needed for the K6 continuity check.
11. **`movimiento_bancario`** (id, importacion_id, extracto_id, cuenta_propia_iban, fecha_contable, fecha_valor, importe_cent, moneda, contraparte_iban, contraparte_nombre_doc, concepto_doc, referencia_e2e, ref_banco, remesa, huella UQ).
12. **`planning_turno`**: one row per shift in a planning import (UQ on importacion_id and id_externo). Each accepted batch is a frozen snapshot.

    | Group | Columns |
    |---|---|
    | Keys | id, importacion_id, id_externo, clave_fragil |
    | Time | fecha, semana_iso, hora_inicio, hora_fin, pausa_min |
    | Hours | horas_planificadas_mil, horas_realizadas_mil, horas_aprobadas_mil |
    | Status | estado: planificado, realizado, aprobado or cancelado |
    | Raw references | objeto_ref_doc, recurso_ref_doc, proveedor_ref_doc, cliente_ref_doc, po_ref_doc |
    | Resolved IDs | objeto_id, recurso_id, proveedor_id, cliente_id |
    | Service and billing | tipo_servicio, tipo_turno, facturable |
    | Rates | tarifa_compra_e4, tarifa_venta_e4 |
    | Raw row | datos_origen_json |

**C. Master data** (mirror of external systems plus local data; TRACKED unless noted)

13. **`proveedor`** (id, nombre, tipo zzp/empresa, kvk, btw_id, regimen_iva, plazo_pago_dias, direccion, email_facturacion, telefono_verificacion, activo, exact_id UQ, trnsprnt_id UQ, rev).
14. **`cliente`** (id, nombre, kvk, btw_id, plazo_pago_dias, requiere_po, tratamiento_iva_defecto, verlegd_elegible, activo, exact_id, trnsprnt_id, rev).
15. **`contacto`** (id, proveedor_id or cliente_id with exactly one set, nombre, email, telefono, funcion, activo, rev).
16. **`objeto`** (id, codigo UQ, nombre, cliente_id, requiere_po, activo_desde, activo_hasta, trnsprnt_id, rev). A NULL `requiere_po` inherits the client's setting.
17. **`recurso`** (id, nombre, tipo empleado/zzp/personal_proveedor, proveedor_id, trnsprnt_id, activo, rev).
18. **`alias`** (tabla, alias_norm, fila_id, origen maestro/manual/config; UQ on tabla and alias_norm). Matching is exact only. An IBAN is never an alias.
19. **`cuenta_bancaria`** (id, titular proveedor/cliente/propia, proveedor_id, cliente_id, iban, nombre_titular, primera_vez_en, primera_fuente; UQ on owner and IBAN). INSERT-ONLY.
    - `primera_fuente`: baseline, maestro_exact, maestro_trnsprnt or verificacion_manual.
    - No code path leads here from an extraction; an import-graph test and a property test check this.
20. **`cuenta_evento`** (id, cuenta_id, tipo, importacion_id, documento_id, metodo, telefono_usado, telefono_ref, persona_contactada, decision_facturas pagar_a_verificada/anular, usuario_id, en, nota, evento_id). APPEND-ONLY.
    - `tipo`: baseline, visto_en_exact, ausente_en_exact, visto_en_trnsprnt, ausente_en_trnsprnt, visto_en_documento, verificada, rechazada, atestada or retirada.
    - `telefono_ref` points to the change that set the phone number used; it must predate the triggering document.
    - A trigger allows `verificada`, `rechazada` and `atestada` only for a human holding `confirmar_iban`.
    - A CHECK requires `metodo` and `telefono_usado` on `verificada`.
21. **`beneficiario_conocido`** (id, iban, nombre, motivo, creado_por, retirada_en). Payees that are not providers (Belastingdienst, payroll, rent), so F7 does not fire on them.
22. **`tarifa_acordada`** (id, sentido compra/venta, proveedor_id, recurso_id, cliente_id, objeto_id, orden_compra_id, tipo_servicio, tipo_turno, unidad, tarifa_e4, vigente_desde, vigente_hasta, fuente, documento_id, rev).
23. **`ciclo_facturacion`** (id, cliente_id, objeto_id, frecuencia semanal/cuatrisemanal/mensual, ancla, dias_gracia, vigente_desde, vigente_hasta, rev).
24. **`orden_compra`** (id, numero, numero_norm, lado cliente/proveedor, cliente_id or proveedor_id, fecha_emision, fecha_inicio, fecha_fin, valor_original_cent, documento_id, cerrada, fuente, rev; UQ on lado, party and numero_norm). With it:
    - **`orden_compra_objeto`** (orden_compra_id, objeto_id);
    - **`orden_compra_modificacion`**, APPEND-ONLY (id, orden_compra_id, fecha, valor_nuevo_cent, fecha_fin_nueva, motivo, documento_id, usuario_id, evento_id). The current or amended value is the latest amendment.

**D. Invoices** (TRACKED)

25. **`factura`**: one table for both directions.

    | Group | Columns |
    |---|---|
    | Kind and source | sentido, tipo factura/nota_credito, origen extraccion/exact/trnsprnt/manual, documento_id, extraccion_vigente_id, fuente_externa, id_externo |
    | Number | numero, numero_norm |
    | Parties | proveedor_id, cliente_id, contacto_id |
    | As printed | emisor_nombre_doc, emisor_kvk_doc, emisor_btw_doc, receptor_nombre_doc, receptor_btw_doc, contacto_nombre_doc |
    | Dates | fecha_factura, fecha_recepcion, fecha_envio, periodo_inicio, periodo_fin, fecha_vencimiento |
    | Terms | plazo_pago_dias, condiciones_pago_doc |
    | Amounts | base_cent, iva_cent, total_cent, tratamiento_iva |
    | Payment | referencia_pago, iban_doc, moneda_doc |
    | Lifecycle | anulada, fusionada_en_id, rev |

    - `iban_doc` is only what the document claims; it is never used for payment.
    - CHECK constraints keep the columns consistent with the direction.
    - There is a partial UQ on (fuente_externa, id_externo) and a partial UQ on documento_id where `origen='extraccion'`.
    - There is deliberately **no** unique key on (provider, number), so B2 can see a duplicate.
    - A merged re-send keeps its own row with `fusionada_en_id` set and is excluded from all totals.
26. **`factura_linea`**: what the paper says; the arithmetic rules read it.

    | Group | Columns |
    |---|---|
    | Keys | id, factura_id, orden, huella_linea |
    | As printed | descripcion_doc, objeto_doc, recurso_doc, unidad_doc, semana_doc, tipo_turno_doc |
    | Dates | fecha_inicio, fecha_fin, fecha_trabajo, semana_iso |
    | Values | unidad, cantidad_mil, tarifa_e4, importe_cent, tipo_iva_pb, tipo_servicio |
    | Audit | rev |

27. **`factura_imputacion`** (id, factura_id, linea_id, objeto_id, recurso_id, orden_compra_id, descripcion, fecha_inicio, fecha_fin, semana_iso, horas_mil, tarifa_e4, importe_cent, tipo_servicio, tipo_turno, facturable, retirada_en, rev).
    - This is the feature list's "Invoice Line / Allocation", and every total reads it.
    - Each line gets one allocation by default. Splitting a line means retiring its allocation and creating new ones.
28. **`factura_iva`** (id, factura_id, tipo_iva_pb, tratamiento, base_cent, cuota_cent, cuota_autoliquidada_cent, deducible, rubrica, rev).
29. **`factura_referencia`** (id, factura_id, linea_id, etiqueta_doc, valor_doc, valor_norm, clase, orden_compra_id, retirada_en, rev).
    - `clase`: po, orden, proyecto, ref_cliente or otra. Code classifies it from a whitelist of labels.
    - `orden_compra_id` is set once the reference matches a PO.
30. **`factura_relacion`** (id, origen_id, destino_id, tipo, importe_cent, estado, fuente, evidencia_doc, retirada_en, rev).
    - `tipo`: acredita, anula, corrige, sustituye or relacionada.
    - `estado`: propuesta, confirmada or rechazada. Only `confirmada` affects balances, VAT and B4.
    - `fuente`: extraccion, exact or manual.
    - A trigger requires both invoices to have the same direction.
31. **`procedencia_campo`**: one mutable row per field (PK tabla, fila_id, campo; WITHOUT ROWID). Its history lives in `cambio_campo`.

    | Group | Columns |
    |---|---|
    | Source of the current value | fuente, fuente_ref |
    | Values | valor_actual, valor_original, valor_original_crudo, fuente_original, valor_automatico |
    | Flags | dudoso, rev_campo |
    | Change | cambiado_en, cambiado_por |
    | Verification | verificado_por, verificado_en, verificado_rev |

    - `fuente` is one of the 7 sources in §13: extraccion, importacion, planning, maestro, manual_entrada, manual_correccion, calculado.
    - `valor_original_crudo` is the printed literal, for example '8.740,00'.
    - `valor_automatico` is the latest value from an automatic source, kept even when a manual value wins.
32. **`nota`** (id, tabla, fila_id, texto, usuario_id, en, evento_id). APPEND-ONLY.

**E. Payments and reconciliation** (TRACKED)

33. **`aplicacion_pago`** (id, factura_id, movimiento_id, importe_cent, fecha_pago, fuente, metodo, estado, regla, motivo, evidencia_documento_id, confirmada_por, confirmada_en, rev).
    - `fuente`: banco, exact or manual. `metodo`: automatica, propuesta or manual. `estado`: propuesta, confirmada or retirada.
    - A manual payment requires a reason.
    - There is no instalment plan and no "approved for payment" state.
34. **`conciliacion`** (id, imputacion_id, planning_turno_id, horas_mil, metodo automatica/manual, regla, retirada_en, rev). The trace from an invoice line to individual shifts (arquitectura.md §5).

**F. Controls**

35. **`ejecucion_reglas`** (id, motivo, hoy, iniciada_en, terminada_en, usuario_id, version_codigo, catalogo_sha256, politica_sha256, resumen_json). `motivo`: ingesta, importacion, edicion, diaria or manual.
36. **`evaluacion`** (regla, tabla, fila_id, clave, resultado, detalle, valores_json, ejecucion_id). CACHE of the latest result of every rule, including passes. `resultado` is ok, fallo, sin_datos or no_aplica; "not evaluable" is never shown as ok.
37. **`hallazgo`**: one row per finding (clave UQ).

    | Group | Columns |
    |---|---|
    | Rule | regla, regla_version |
    | Identity and evidence | clave (rule, target and key), huella (compared values, their sources, the policy parameters used) |
    | Target | tabla, fila_id, factura_id |
    | Classification | severidad, calidad, ambito, pegajosa, anulable |
    | Content | titulo, detalle, valores_json |
    | Lifecycle | estado, primera_vez_en, ultima_vez_en, ultima_ejecucion_id |

    `estado` is abierto, desaparecido, resuelto or aceptado. `pegajosa` marks a sticky rule.
38. **`hallazgo_objetivo`** (hallazgo_id, tabla, fila_id, campo, papel principal/relacionado). Lets one finding cover several invoices and badge a specific field.
39. **`hallazgo_evento`** (id, hallazgo_id, tipo, huella, causa_evento_id, ejecucion_id, usuario_id, en, nota). APPEND-ONLY. This is the warning resolution history.
    - `tipo`: detectado, cambio_evidencia, desaparecido, cerrado_automatico, resuelto, aceptado or reabierto.
    - `causa_evento_id` is the edit or import that caused it.
40. **`anulacion`** (id, hallazgo_id, huella, motivo, usuario_id, en, vigente_hasta, segunda_firma_usuario_id, segunda_firma_en, autoaprobada). APPEND-ONLY.
    - Effective only while the finding's huella equals the override's huella and the expiry has not passed.
    - A trigger refuses overrides on rules that cannot be overridden.
41. **`excepcion`** and **`excepcion_hallazgo`**: the work item.

    | Group | Columns |
    |---|---|
    | What | titulo (the Issue), descripcion |
    | Target | tabla, fila_id, factura_id |
    | Status and owner | estado, responsable_id |
    | Waiting | esperando_a, fecha_seguimiento |
    | Resolution | resolucion, resolucion_notas |
    | Dates | creada_en, creada_por, resuelta_en, resuelta_por |
    | Audit | rev |

    - `estado`: abierta, asignada, esperando_externo or resuelta.
    - `resolucion`: corregido, aceptado, anulado, no_procede or condicion_desaparecida.
    - CHECKs: `asignada` needs an owner; `resuelta` needs a resolution.
42. **`revision`** (id, factura_id, resultado revisada/devuelta, huella_contenido, autorrevisada, usuario_id, en, nota, evento_id). APPEND-ONLY. A trigger allows only a human with `revisar_factura`.
43. **`prioridad_manual`** (id, entidad, entidad_id, nivel, motivo, usuario_id, en, hasta). APPEND-ONLY. It can only raise a priority.
44. **`factura_estado`** (factura_id, estado_pago, pendiente_cent, dias_vencida, estado_revision, calidad, editada, suplementada, corregida, sin_resolver, nivel, puntos, suelo, motivos_json, huella_contenido, ejecucion_id). CACHE, rebuilt on each run and daily.
    - It holds the columns that the §18 filters query with SQL.
    - **`prioridad`** is the same kind of cache for exceptions, POs, providers, clients, Objects and BTW quarters.

**G. BTW**

45. **`periodo_btw`** (id, ano, trimestre, inicio, fin, limite_presentacion, limite_pago, estado, presentado_en, presentado_por, referencia_presentacion, importe_declarado_cent, hoja_documento_id, hoja_sha256, nota, rev; UQ on year and quarter).
    - `estado`: abierto, listo_revision or presentado.
    - A trigger allows `presentado` only for a human with `gestionar_btw`, with a filing reference and the worksheet's hash. It never goes back.

**Views** (independent of today's date; integer sums)

| View | Purpose |
|---|---|
| `v_cuenta_estado` | Current state of each bank account |
| `v_factura_saldo` | Total, credited, paid, open balance, base payment status |
| `v_imputacion_vigente` | Active allocations of invoices that are not cancelled or replaced |
| `v_turno_vigente` | Newest accepted planning batch for each date |
| `v_planning_estado` | Per shift: reference hours, hours reconciled to purchase and to sales |
| `v_po_consumo` | PO consumed, remaining, percentages |
| `v_objeto_periodo` | Per Object, by ISO week and month: revenue, costs, margin, hours |
| `v_proveedor_totales`, `v_cliente_totales` | Lifetime totals |
| `v_cliente_cobro` | Average payment time, late payments |
| `v_btw_linea` | VAT lines with quarter and rubric |
| `v_campo_calidad` | Data-quality state per field |
| `v_factura_ediciones` | Manual-edit flags per invoice |
| `v_factura_listado` | One row per invoice for search |

Anything that depends on today's date, on statistics or on a forecast is computed in Python with `hoy` passed in.

**Where each status and value lives**

| Status or value | Comes from |
|---|---|
| Outstanding / Overdue / Paid / Cancelled-Credited | `v_factura_saldo` plus `hoy`, cached in `factura_estado`. Paid means the open balance is within tolerance; a partial payment stays Outstanding or Overdue with the remaining balance and K2. |
| Unreviewed / Needs Review / Reviewed | The latest `revision` compared with the current `huella_contenido` (current values plus the evidence of open findings). Needs Review when there is an open blocking or held finding, an unverified doubtful field, an unresolved manual change, or the last review was "devuelta". |
| Data quality | `v_campo_calidad`, in this order: faltante, discrepancia, anomalia, dudoso, verificado. A field with none of these shows neutral, never green. |
| Manual-edit flags | `procedencia_campo`. "Unresolved" means a manual value that differs from `valor_automatico` and is not verified, or a conflict after re-extraction. |
| IBAN state | `v_cuenta_estado`. The latest human event wins; otherwise heredada, or registered but unverified. |
| Exception status, BTW status | Set by humans and audited. |
| Priority | `prioridad.py`, written to the caches. |

---

## 6. Modules

**New**

| Module | Responsibility |
|---|---|
| `almacen/__init__.py` | `abrir()` (settings, minimum version, Row factory) and `transaccion()` (BEGIN IMMEDIATE) |
| `almacen/migrar.py`, `almacen/sql/00NN_*.sql` | Ordered migrations, one per build step, sha-checked |
| `almacen/documentos.py` | Write-once document store; `abrir()` logs each opening; `verificar()` re-hashes |
| `almacen/unidades.py` | The only Decimal-to-integer converter (`_cent`, `_mil`, `_e4`, `_pb`); canonical JSON that rejects floats; sha256 helpers |
| `auditoria.py` | Writes and seals `evento`; `verificar_cadena()`; `anclar()` puts the chain head in the daily report and `out/anclas.log`; `historial()` timelines |
| `dominio.py` | Enums: Sentido, Fuente (7), Calidad (5), EstadoPago, EstadoRevision, EstadoExcepcion, Prioridad, Severidad, TipoRelacion, EstadoBtw, Permiso |
| `campos.py` | Field registry (type, required per direction, editable, permission to supplement vs correct, external authority, critical) and `crear/fijar/retirar/verificar_campo`. The **only** writer of TRACKED tables (details below). |
| `permisos.py` | Permission catalogue, roles, `exigir()`, system actors, SOD1–5 predicates under the si_hay_dos policy |
| `politica.py` | Loads `config/*.yaml`, records `politica_version`, refuses to relax the catalogue's hard rules |
| `reloj.py` | Injectable `hoy` in Europe/Amsterdam (needs `tzdata` on Windows); ISO week helpers moved from dashboard.py; quarters, BTW deadlines, cash-flow windows |
| `identidad.py` | Normalises names and resolves them exactly: btw-id, then KvK, then confirmed alias. Never by IBAN, never fuzzy. |
| `compat.py` | Upcasts v1 extractions to the v2 shape when read, and lists the fields v1 never asked for |
| `ingesta.py` | The single intake path for the CLI and the server: document store, extraction according to the cache policy, typed rows through `campos`, recompute. The intake route sets the direction. |
| `legado.py` | `registros_legado()` and `registros_resueltos()`: today's record dicts built from the store |
| `importadores/` | `base`, `canonico`, `tabular`, `camt053`, `mt940`, `extracciones`, `registrar` |
| `reglas/` | `base`, `catalogo`, `motor`, plus one module per rule family: calidad, identidad, unicidad, fechas, aritmetica, iva, bancaria, pagos, planning, venta, ordenes, relaciones, anomalias |
| `hallazgos.py` | Stores rule results; finding lifecycle, sticky rules, overrides, field badges |
| `excepciones.py`, `revision.py`, `prioridad.py` | §15 and §16 |
| `conciliacion.py` | Planning to allocations; proposes an Object from planning |
| `pagos.py` | Bank matching, open balance, payment status |
| `relaciones.py` | Relationship proposals and their effects |
| `ordenes_compra.py` | PO consumption, forecast, value of planned and unbilled work |
| `btw.py`, `flujo_caja.py` | §8 and §7 |
| `servicios.py` | Typed commands for §10, §15 and §19 (permissions below). Each checks the permission, requires a reason, checks `rev` (concurrency) and `peticion_id` (idempotency), writes through `campos`, recomputes, and returns a **Diferencia**: results that changed, findings opened, closed or reopened, reviews invalidated, priority changes, affected totals. |
| `consultas.py` | Overviews (§3–5), search with whitelisted filters (§18), invoice detail (provenance, evaluations, reconciliation trace, history), dashboard (§17), contract v2 |
| `reextraccion.py` | Selective, budgeted re-extraction (sync or batch); a new extraction becomes current only after the score gate |
| `consola.py`, `consola_assets.py` | Internal console. All document text goes in through `textContent`. |

How `campos.fijar` decides:
- A manual value with no automatic original becomes `manual_entrada`, otherwise `manual_correccion`.
- A manual value equal to the original reverts the field to its original source.
- An automatic source never overwrites a manual value. It only updates `valor_automatico`, and M1 fires if the two differ.
- Fields owned by Exact or TRNSPRNT are refused; the correction belongs in that system.

Which permission each command needs:

| Permission | Commands |
|---|---|
| `anadir_informacion` | Fill a missing value, add a note |
| `editar_extraccion` | Correct a field, split, add or exclude a line, verify a field, revert a change |
| `cambiar_objeto` | Change the Object allocation, add an Object or resource alias |
| `cambiar_po` | Change the PO allocation, register or amend a PO |
| `marcar_pagada` | Mark paid, confirm a proposed payment |
| `anular_acreditar` | Link or confirm relationships, cancel an invoice, merge a duplicate |
| `resolver_aviso` | Handle exceptions, close a finding whose condition is gone |
| `anular_aviso` | Override a finding |
| `confirmar_iban` | Verify, reject or attest an IBAN; set the verification phone |
| `revisar_factura` | Mark reviewed or send back |
| `gestionar_btw` | BTW status |
| `importar_datos` | Run importers |
| `admin` | Users, roles, policy, known non-provider payees |

**Changed**
- **`parsing.py`:** adds `detectar_moneda`, `parse_importe` (returns the amount and its currency), `es_unidad_hora`, `parse_plazo_pago` and `normalizar_referencia`. `parse_amount` stays for compatibility but is not used where currency matters.
- **`checks.py`:** the pure functions stay and are wrapped by `reglas/`; fixes the E3 label.
- **`dashboard.py`:**
  - the detectors delegate to `reglas/unicidad`, and the v1 contract stays as it is;
  - B4 becomes "revisar";
  - G3 groups by provider identity;
  - `detectar_ibanes` stops naming the oldest document IBAN as the reference.
- **`facturacion.py`:** uses `es_unidad_hora`, reads Object-to-client mapping and rates from the store, and remains a projection.
- **Extractor files** (`schema.py`, `prompts.py`, `config.py`, `extract.py`, `cache.py`, `scoring.py`, `coste.py`, `pricing.py`): see section 10.
- **`serve.py`:** hardening (section 11, step 0), `/api/v2` read endpoints and `POST /api/v2/acciones`.
- **`cli.py`:** new commands: `db init|migrar|verificar`, `importar-out`, `importar <fuente> <tipo> <fichero> [--mapeo] [--simular]`, `recalcular [--simular]`, edit commands, exception commands, `iban verificar|rechazar|atestar`, payment and relationship commands, `btw estado`, `auditoria verificar|historial`, `reextraer`, `usuario`.
- **`report.py`, `panel.py`:** read their records from the store.

**Configuration and docs**
- Config files: `config/reglas.yaml` (tolerances and thresholds with effective dates), `config/prioridad.yaml`, `config/btw.yaml`, `config/empresa.yaml` (BMS's legal identity, btw-id and own IBANs), and `config/importacion/<fuente>-<tipo>-vN.yaml` mappings.
- `tzdata` is added to pyproject; `/datos/` to .gitignore.
- Docs: new `docs/modelo-datos.md`. Update `validacion-facturas.md` (generated from the rule catalogue), `integracion-web.md` (contract v2) and the README.

**Tests**
- `conftest.py`: an in-memory database with all migrations applied, entity builders and a fixed clock.
- Files: `test_almacen`, `test_auditoria`, `test_campos`, `test_migracion_out`, `test_equivalencia_legado`, `test_reglas_*` (table-driven per family), `test_hallazgos`, `test_prioridad`, `test_importadores` (one contract test per mapping), `test_pagos`, `test_flujo_caja`, `test_btw`, `test_serve_seguridad`, `test_alcance_v1`, `test_pureza_reglas` (AST), `test_rendimiento`.

---

## 7. Checks

**How to read the tables**
- E is incoming (purchase), S is outgoing (sales).
- On fail: B = Bloqueo, R = Retención, A = Aviso, as in validacion-facturas.md §2.
- "No override" means the rule cannot be overridden. "Sticky" means the finding never closes itself.
- The last column is the §16 priority input.
- Tolerances and thresholds come from `config/reglas.yaml`.

**Data and identity**

| ID | Check | On fail | Override / sticky | Priority input |
|---|---|---|---|---|
| Q1 | Required field missing for the direction: number, counterparty, date, period, base, VAT or regime, total | R (B for number, total, counterparty) | no override | otra |
| Q2 | Critical field doubtful (`low_confidence_fields` or parse error) and not verified | R | no override | otra |
| Q3 | `document_notes` holds flagged text (sign of an injection attempt) | A + exception | overridable | otra |
| Q4 | Original document not retained | A | overridable | otra |
| X1 | Not EUR (currency field, symbol in the amounts, bank currency). Excluded from every total. | B | no override, sticky | otra |
| M1 | Manual value differs from the latest automatic value and is not verified (the "unresolved" flag) | A, quality "discrepancia" | — | otra |
| Z1 | Source older than its freshness limit. Dependent rules return `sin_datos`. | A + banner | — | otra |
| Z2 | Import rows rejected, or unknown party, Object or resource | R | no override | otra |
| A0 | Counterparty unknown or ambiguous | R | no override | otra |
| A1, A3, A5 | As in the catalogue (A5 blocks when the btw-id is missing and KOR is not mentioned) | R / A / B | — | otra / VAT |
| A2 | Printed name, KvK or btw-id differs from the master data | R | overridable | otra |
| A7 | Details changed versus the provider's own history (btw-id or KvK: R; name or address: A) | R / A | overridable; sticky for btw-id and KvK | otra |
| A8 | Not addressed to BM Support BV (compared with `config/empresa.yaml`). On the outgoing route, an issuer other than BMS means misrouted. | R (B if misrouted) | overridable | otra |

A4 and A6 need KvK and VIES lookups, so they are periodic checks outside V1.

**Duplicates**

| ID | Check | On fail | Override / sticky | Priority input |
|---|---|---|---|---|
| B1 | Invoice number present | B | no override | — |
| B2 | Same counterparty and normalised number, not merged and not linked | B | close by merge or link; override needs a 2nd signer; sticky | exact duplicate |
| B3 | Same counterparty, total within 0,01, at most 14 days apart, compatible periods, different number | R | overridable, sticky | duplicate |
| B4 | Overlapping charge periods (per Object when lines name one); confirmed relationships excluded | R | overridable, sticky | duplicate |
| B5 | Duplicate hours: same resource, Object and date on two unrelated lines, or a shift reconciled to more purchase hours than it has | R | overridable, sticky | duplicate |
| V7 | Duplicate billing: the B2, B3 or B5 cases on outgoing invoices, or a shift billed for more hours than it has | R | overridable, sticky | duplicate |

**Dates**

| ID | Check | On fail | Priority input |
|---|---|---|---|
| C1 | Invoice date present and not in the future | R | otra |
| C2 | Service period present (header or lines) | B | otra |
| C3 | Invoice date before the end of the period | A | otra |
| C4 | Date or period in a quarter already marked filed, or changed after filing | A + added to the quarter's list | soft VAT |
| C5 | Printed due date shorter than the agreed payment terms | A | otra |

**Arithmetic and VAT**

| ID | Check | On fail | Override / sticky | Priority input |
|---|---|---|---|---|
| D1 | Breakdown present | E: B, S: R | no override | otra |
| D2 | Sum of lines equals the base (0,01 per line plus 0,02) | E: B, S: R | no override | otra |
| D2b | Quantity times rate equals the line amount (0,01) | E: B, S: R | overridable | otra |
| D3 | Base times rate equals the VAT, per rate | B | no override | hard VAT |
| D4 | Base plus VAT equals the total | B | no override | otra |
| D6 | The VAT breakdown adds up to the header | B | no override | hard VAT |
| I1 | A line's active allocations add up to the line amount | R | no override | otra |
| E0 | VAT information missing (treatment unknown, or standard VAT without rate or amount) | R | no override | soft VAT |
| E1 | Rate differs from the provider's registered regime | R | overridable | soft VAT |
| E2 | Regime changed versus the previous invoice | R | overridable, sticky | soft VAT |
| E3 | KOR, yet VAT charged | B | no override | hard VAT |
| E4 | Reverse charge, yet VAT charged, or BMS's btw-id missing | B | no override | hard VAT |
| E5 | Cumulative amount paid approaching the KOR threshold | A | — | soft VAT |
| E7 | Unusual rate or treatment: rate not 0, 9 or 21 (policy list); 0% or reverse charge on an outgoing invoice to a client not marked eligible | R | overridable | soft VAT |

**Bank details**

None of these can be overridden, and all are sticky. They close only through a verification, a rejection or a change in the data.

| ID | Check | On fail |
|---|---|---|
| F1 | IBAN fails the mod-97 check digit | B |
| F2 | The IBAN on the document is not a payable account of this provider | B |
| F3 | New or changed IBAN versus the registry (from a document, Exact or TRNSPRNT); needs a callback verification | B |
| F4 | IBAN registered for another provider, or wording about factoring, cessie or G-rekening | B + escalation |
| F5 | IBAN added, changed or removed in a master import after the baseline | B |
| F6 | Exact and TRNSPRNT disagree on a provider's IBAN | B |
| F7 | A bank debit matched to a provider went to an IBAN that is not payable for it (and is not a known non-provider payee) | B, and at least Urgent |
| F8 | Verification ineffective: the number called is not the master phone that existed before the document, the phone changed within the cool-down, or the person lacked the permission | B |
| F9 | The verification phone number changed (starts the cool-down) | A |
| F10 | An outgoing invoice shows an IBAN that is not one of BMS's own accounts | R |

**Payments**

| ID | Check | On fail | Override / sticky | Priority input |
|---|---|---|---|---|
| K1 | Overdue (incoming: past due; outgoing: more than N days past due) | A + exception | overridable | days overdue |
| K2 | Confirmed payments do not equal the open balance (partial or overpaid) | E: R, S: A | no override, sticky | otra |
| K3 | Marked paid by hand, still no bank evidence after N days | A | overridable | otra |
| K4 | Double payment: two debits for one invoice, or same party, amount and reference within 30 days | B | no override, sticky | duplicate |
| K5 | Paid while the invoice was Blocked | R | no override, sticky | otra |
| K6 | Bank statement continuity break: opening balance differs from the previous closing balance, or a sequence number is missing | B (for all statuses after the gap) | no override, sticky | otra |
| K7 | Bank movement still unmatched after N days | A | overridable | otra |
| K8 | Bank and Exact disagree on a payment | R | no override | otra |

**Planning, incoming**

These return `sin_datos` until planning data is imported. G1 turns blocking once planning is declared mandatory.

| ID | Check | On fail | Override | Priority input |
|---|---|---|---|---|
| G1 | No assignment for the provider or resource in the invoiced period | B | needs a 2nd signer | planning |
| G2 | Invoiced hours versus approved hours, compared at the finest level both sides carry (resource and day, then Object and day, then Object and week); 0,25 h per day | R | overridable | planning |
| G3 | Rate versus the agreed rate (most specific first: resource + Object + shift type, Object + shift type, party + shift type, party), else the shift's rate in planning, else history. An ambiguous match gives `sin_datos` plus an exception. | R; B above the configured excess | overridable (the B part needs a 2nd signer) | planning |
| G4 | Object versus planning | R | overridable | planning |
| G5 | Period and ISO week versus planning | R | overridable | planning |
| G6 | Surcharges billed at their own agreed rate | R | overridable | planning |
| G7 | A newer planning batch changes hours already reconciled to this invoice | A | overridable | planning |

**Outgoing invoices**

| ID | Check | On fail | Priority input |
|---|---|---|---|
| V1 | Billed hours versus approved billable shifts | R | planning |
| V2 | The Object exists, belongs to the invoiced client and is active | R | planning |
| V3 | Period versus planning | R | planning |
| V4 | Billing rate versus the agreed sale rate (too high and too low) | R | planning |
| V5 | Approved billable hours missing inside a client, Object and period that was billed | R | missing billing |
| V6 | Potential unbilled work: the period ended more than the grace days ago, there are approved billable hours, and no outgoing line covers them. Valued at the agreed sale rate, else marked "estimado". | R | unbilled work |
| V8 | Billing period missing according to the billing cycle | R | missing billing |
| V9 | Planning changed after billing (rule 9) | R | planning |

All of these can be overridden.

**Purchase orders**

PO consumption is the base (excluding VAT) of allocations on invoices that are not cancelled or replaced, minus confirmed credits, ordered by invoice date and then by ID.

| ID | Check | On fail | Override / sticky | Priority input |
|---|---|---|---|---|
| P1 | PO valid: it exists, belongs to the same party, covers the Object, the work dates fall inside its validity, and it is not closed | R | overridable | PO limit |
| P2 | PO missing where one is required | R | overridable | PO limit |
| P3 | Unknown or wrong PO (not found, or another party or Object) | R | overridable | PO limit |
| P4 | Invoice exceeds the value remaining before it | R | overridable, sticky | hard PO limit |
| P5 | 80% or more consumed | A | — | PO limit |
| P6 | Fully consumed, and still invoiced against | R | overridable | hard PO limit |
| P7 | Expires within 30 days with value left (R if already expired with planned work after the end) | A / R | overridable | PO expiration |
| P8 | Planned work times the sale rate exceeds the remaining value | A | — | PO limit |
| P9 | Forecast exhaustion (8-week burn rate) earlier than 14 days before the end date | A | — | PO limit |
| P10 | Invoiced plus unbilled plus planned exceeds the PO value | R | overridable | hard PO limit |

**Relationships and anomalies**

| ID | Check | On fail | Override / sticky | Priority input |
|---|---|---|---|---|
| R1 | A credit note or correction refers to an unknown invoice | R | overridable | otra |
| R2 | Credits exceed the original | R | no override, sticky | otra |
| R3 | Original and replacement both outstanding, or both paid | B | no override, sticky | duplicate |
| R4 | Credit note without a confirmed relationship | A | — | otra |
| R5 | Relationship proposed by the extraction, waiting for confirmation | A | — | otra |
| U1 | Unusual amount compared with the counterparty's earlier bases (method below) | A + exception | overridable | otra |

U1 compares against the counterparty's earlier bases on invoices that were not cancelled:
- with 6 or more of them, flag when abs(x − median) / (1.4826 · MAD) > 3.5; if MAD is 0, flag when abs(x − median) / median > 0.5;
- with 3 to 5, flag when x > 2 × median or x < 0.5 × median;
- with fewer than 3, the rule returns `sin_datos`.

**How the feature list's checks map to these IDs**
- **§1 incoming:**

  | Feature-list check | Rule IDs |
  |---|---|
  | Hours, Object, Period ↔ Planning App | G2, G4, G5 (plus G1) |
  | Rate ↔ agreed rate | G3 |
  | Invoice total ↔ invoice lines | D2, D2b, D4 (plus I1) |
  | VAT calculation | D3, D6, E3, E4 |
  | Duplicate invoice | B2, B3 |
  | Duplicate hours | B5 |
  | Overlapping charge periods | B4 |
  | Provider details ↔ historical data | A2, A7 |
  | IBAN ↔ verified IBAN | F2 |
  | Changed IBAN | F3, F5, F6 |
  | Unusual invoice amount | U1 |

- **§2 outgoing:**

  | Feature-list check | Rule IDs |
  |---|---|
  | Hours, Object, Period ↔ Planning App | V1, V2, V3 |
  | Billing rate ↔ agreed rate | V4 |
  | Missing billable hours | V5 |
  | Potential unbilled work | V6 |
  | Duplicate billing | V7 |
  | Missing billing period | V8 |
  | Invoice total ↔ invoice lines | D2, D4 |
  | PO validity | P1 |
  | PO remaining value | P4 |

- **§6 PO alerts:**

  | Feature-list alert | Rule ID |
  |---|---|
  | PO approaching spending limit | P5 |
  | PO fully consumed | P6 |
  | Invoice exceeds remaining PO | P4 |
  | Missing PO | P2 |
  | Unknown / incorrect PO | P3 |
  | PO approaching expiration | P7 |
  | Planned work exceeds remaining PO | P8 |
  | Forecast PO exhaustion | P9 |
  | Expected amount over PO | P10 |

- **§8 VAT:** missing information is E0, incorrect calculation is D3 and D6, unusual treatment or rate is E1, E2 and E7. "Invoices requiring VAT review" are the quarter's invoices with open VAT findings, plus C4.
- **Added beyond the list:** Q1–Q4, X1, M1, Z1–Z2, A0, A8, C5, F1, F4, F7–F10, K1–K8, G6, G7, V9, R1–R5 and I1.

**How the engine works**
- A rule is a pure function over a frozen snapshot. The snapshot holds current values with their sources, master data, the current planning batch, payments, POs, confirmed relationships, the policy and `hoy`.
- Rules never touch the database, the clock, the environment or the network. An AST test enforces this, and a recording proxy checks that each rule reads only what it declares.
- Results are sorted. Every command and every import ends with a full recompute in the same transaction.
- `sin_datos` never counts as ok.

**Finding lifecycle**
- A change in a finding's huella reopens it if it had been resolved or overridden.
- A non-sticky finding whose condition disappears closes with the edit or import that caused it recorded.
- A sticky finding whose condition disappears stays open as "condición desaparecida" until a person closes it.
- An override needs `anular_aviso` and a reason of at least 10 characters, and applies only to rules that allow it. It is tied to the huella and can expire.
- If a finding disappeared because user U edited one of its fields, that edit stays "unresolved" until it is verified, by someone else when a second person exists.

**Exceptions**
- One exception per affected entity: invoice, PO, provider, quarter, bank movement or import.
- It groups that entity's open blocking and held findings, plus warning-level findings whose rule creates exceptions.
- It cannot be resolved while a linked blocking finding is open and not overridden.
- The follow-up date for "waiting external" defaults to at most `hoy` + 14 days.

**Review**
- Only a person with `revisar_factura` can mark an invoice reviewed, and only when it has no open blocking or held finding that isn't overridden.
- The review stores the invoice's content fingerprint and is invalidated by any later change.
- A clean invoice is labelled "sin objeciones del sistema", never "aprobada".

---

## 8. Priority algorithm

`prioridad.calcular(entradas, hoy, pesos) -> (nivel, puntos, suelo, motivos)` is a pure function. Its weights live in `config/prioridad.yaml`, recorded by hash in `politica_version`.

**Inputs (§16)**
- Days until the payment deadline, and days overdue.
- The amount (absolute base).
- Planning discrepancies (G2–G6, V1–V4) and their value: the sum of the hour differences times the rate.
- Changed IBAN (F family).
- Duplicates: exact (B2) or probable (B3–B5, V7, K4, R3).
- Missing billing (V5, V8) and unbilled work (V6), with their value and the weeks past the grace period.
- PO limit (soft P1–P3, P5, P8, P9; hard P4, P6, P10) and PO expiration (P7, days left).
- VAT: hard (D3, D6, E3, E4) or soft (E0–E2, E7, C4), plus the days until the BTW deadline.
- Other anomalies.
- Whether the invoice needs action: it has an open exception, or it is not reviewed.

**Layer 1: floors.** A floor is the minimum level, set by findings that are open and not effectively overridden.
- **Blocked:** any finding with severity Bloqueo, namely:
  - B1, B2, C2, A5, X1, K4, K6, R3;
  - D1, D2 and D2b on incoming invoices; D3, D4, D6, E3, E4;
  - the F family (F10 is only a hold);
  - G1 when planning is mandatory, Q1 for number, total or counterparty, and A8 when misrouted.
- **Urgent:**
  - B3, B4, B5, V7, F7, P4, P6, P10, K5;
  - any VAT finding when the BTW deadline is 7 days away or less;
  - an incoming invoice more than 30 days overdue that needs action;
  - an outgoing invoice more than 60 days overdue.
- **Attention:** any open held finding, any open exception, an unverified doubtful field (Q2) or an unresolved manual change (M1). This includes sticky findings whose condition has disappeared but that nobody has closed yet.

**Layer 2: points.** The deadline, overdue and amount points count only when the invoice needs action.

| Input | Points |
|---|---|
| Payment deadline (incoming) | due in 0–3 days: 20; in 4–7 days: 10 |
| Days overdue, incoming | 1–14 days: 15; 15–30 days: 25; over 30 days: 35 |
| Days overdue, outgoing | 1–14 days: 10; 15–30 days: 20; 31–60 days: 30 |
| Amount | 2.500 or more: 5; 10.000 or more: 10; 25.000 or more: 20 |
| Planning discrepancy | 15; plus 10 if worth 500 € or more; plus 10 more if 2.500 € or more |
| Missing billing (V5, V8) | 20 |
| Unbilled work (V6) | under 1.000 €: 15; otherwise 25; plus 5 per full week past the grace period, at most 20 extra |
| Soft PO limit | 10 |
| PO expiration (P7) | within 30 days: 10; within 7 days: 20 |
| Soft VAT finding | 20; plus 15 if the BTW deadline is 14 days away or less |
| Other anomaly | 10 per distinct rule, at most 20 |
| Waiting external, follow-up date in the future | deadline and overdue points halved |
| Waiting external, follow-up date passed | 10 |

Points map to a level: 0–19 is Normal, 20–39 is Attention, 40 or more is Urgent. Points can never make an invoice Blocked.

**Final level** is the highest of the floor, the points level and any active manual raise. A person can raise a priority with a reason, and the raise is audited and can expire. Nobody can lower one. Blocked always has a named rule behind it.

**Reason for priority.** The floor's reason comes first, followed by each contribution, rendered from templates. For example: "Bloqueada: IBAN NL..4300 no verificado para Van Dijk BV (F3) · vence en 2 días +20 · importe 12.400,00 ≥ 10.000 +10".

**Aggregation and ordering**
- An exception takes the maximum of its findings' floors and its invoice's level.
- A provider, client, Object, PO or quarter takes the maximum of its children.
- Ordering: level (highest first), then points (highest first), then due date (earliest first, empty last), then absolute amount (largest first), then ID.
- The input fingerprint and the policy hash are stored with every result. The result is recomputed in every transaction and once a day by `recalcular`.

---

## 9. Importer interfaces

```python
class Lector(Protocol):                      # pure: bytes in, canonical records out
    fuente: str                              # extracciones | exact | trnsprnt | banco | maestro_csv | po_csv
    tipo: TipoImportacion                    # proveedores, clientes, contactos, objetos, recursos, cuentas,
                                             # tarifas, ordenes_compra, ciclos, facturas_venta, facturas_compra,
                                             # pagos_exact, extracto, planning
    formato: str                             # "csv:exact-crediteuren-v1", "camt053", "mt940:ing", ...
    def reconoce(self, contenido: bytes, nombre: str) -> bool: ...
    def leer(self, contenido: bytes, nombre: str, mapeo: Mapeo | None) -> LoteLeido: ...

@dataclass(frozen=True)
class LoteLeido:
    tipo: TipoImportacion; formato: str; fichero_sha256: str
    mapeo_id: str | None; mapeo_sha256: str | None
    exportado_en: datetime | None; cubre_desde: date | None; cubre_hasta: date | None
    completo: bool                           # full snapshot: items missing from it count as withdrawn
    registros: tuple[RegistroCanonico, ...]
    rechazos: tuple[Rechazo, ...]            # (fila, motivo, crudo)
    avisos: tuple[str, ...]

def registrar_lote(conn, lote: LoteLeido, *, lanzado_por: Usuario,
                   simular: bool = False) -> ResultadoLote: ...   # the only writer
```

**Canonical models.** They are pydantic models with `extra='forbid'`, using Decimal and date types, and each keeps its raw source row.
- `TurnoCanonico`: shift ID, date, start, end, break, planned, worked and approved hours, status, Object, resource, provider and client references, service type, shift type, billable flag, purchase and sale rates, PO reference.
- `ExtractoCanonico` and `MovimientoCanonico`: own account, sequence number, opening and closing balances; signed amount, currency, booking and value dates, counterparty IBAN and name, end-to-end ID, remittance information, bank reference.
- `FacturaVentaCanonica` and `LineaVentaCanonica`: number, client, dates, due date, terms, base, VAT per rate, total, PO references, related invoice; lines with Object, resource, period, hours, rate, amount and PO.
- `FacturaCompraCanonica`: only if TRNSPRNT self-bills providers.
- `PagoExactCanonico`: open items and payments from Exact.
- `OrdenCompraCanonica` and `ModificacionPOCanonica`.
- `ProveedorCanonico`, `ClienteCanonico`, `ContactoCanonico`, `CuentaBancariaCanonica`, `ObjetoCanonico`, `RecursoCanonico`, `TarifaCanonica`, `CicloCanonico`.

**What `registrar_lote` guarantees**
- **Safe to re-run:** importing the same file twice does nothing (unique source, type and file hash). Each record is matched by its natural key. The raw file goes into the document store.
- **Atomicity per source:** all-or-nothing for `extracto`, `planning`, `cuentas`, `facturas_*` and `pagos_exact`. Other master data is loaded row by row, and the rejected rows become finding Z2.
- **Provenance:** values are written through `campos` with source `importacion` and reference `importacion:N`.
- **What an import can never do:**
  - overwrite a manual value; a disagreement raises M1 instead;
  - edit a field owned by Exact or TRNSPRNT;
  - write a verified state;
  - enter an IBAN other than as a `cuenta_bancaria` row plus a `visto_en_*` event.
- **Full snapshots:** an item missing from a full snapshot gets an `ausente_*` event or is retired.
- **Unknown references:** an unknown party, Object or resource becomes a finding. Nothing is created automatically, and matching is exact only.
- **Actors and freshness:** the import runs as the system importer, launched by a person holding `importar_datos`, and both are recorded. `exportado_en` drives source freshness.
- **Recompute and dry run:** rules re-run in the same transaction. `--simular` reports what would be new, changed or rejected without writing.

**By source**

| Source | Status | Details |
|---|---|---|
| Existing extractions (`out/*.json`, v1 and v2) | now | Finds each PDF by hash and copies it into the store, stores the extraction verbatim, then runs ingestion. Makes zero API calls. |
| Master data (Exact CSV exports, or a sheet filled in by hand) | now | Suppliers and customers with bank accounts, payment conditions, VAT code and the designated phone field; Objects, resources and aliases; agreed rates; billing cycles. A one-off seed from `config/tarifas.yaml`. |
| Exact | CSV now; REST later | Sales invoices and lines, with cost centre or project mapped to an Object. Open items and payments, with precedence bank, then Exact, then manual. REST later goes through the single process that owns the token (sistemas.md). Nothing is ever written to Exact. |
| Bank | now | CAMT.053 versions .001.02 and .001.08, read with ElementTree. Files with a DOCTYPE or ENTITY are rejected, each TxDtls is one movement, and the balances and sequence number feed K6. MT940 with bank-specific `:86:` profiles (ING, ABN AMRO, Rabobank). Bank CSV presets are flagged "sin saldos", so K6 is not evaluated on them. The statement account must be one of BMS's own accounts, a non-EUR row becomes X1, and duplicates are dropped by hash, which includes the position of identical rows in the file. |
| TRNSPRNT | mapping now; live when the format is known | A CSV mapping built now against a synthetic fixture; an API reader later produces the same records. Snapshot batches; a synthetic key fallback flagged as fragile; a weekly pivoted export is read at week level. Self-billed purchase invoices come in structured, with no model involved. |
| POs | now | CSV or YAML typed by a person (needs `cambiar_po`). Amendments are separate rows. |

**Mappings.** Each CSV layout gets a versioned YAML file. It declares:
- the delimiter, the encoding (utf-8-sig or cp1252) and the decimal separator;
- the date formats and the header row;
- which column feeds which field, plus value maps;
- derived fields, such as hours = end − start − break;
- sign rules, such as ING's "Af/Bij";
- a header fingerprint, so `reconoce()` can detect the format.

Adding a new layout means writing one YAML, one anonymised fixture and one expected-output JSON (a contract test). XLSX support would be an optional extra (openpyxl); until then, the instruction is to export as CSV.

---

## 10. Extractor changes

**Unchanged on purpose**
- No tools and no network.
- Output is forced to the schema.
- Amounts are copied literally.
- Injected text goes into `document_notes`.
- Nothing from the database enters the prompt: no master data, no IBAN list, no PO list.
- `build_request` and `ExtractionRecord` keep their shape, so `test_extraction_contract` stays green.

**Schema v2.** `SCHEMA_VERSION` becomes "2" and `PROMPT_VERSION` is bumped.
- Every new field is required but nullable, as today.
- Every model gets `extra='forbid'`, so `model_json_schema()` emits `additionalProperties:false`.
- No recursion, no min/max and no length constraints.

New header fields:
- `document_type`: invoice, credit_note, corrected_invoice, replacement_invoice, cancellation or unknown. Only what the document itself declares.
- `related_invoices`: a list of {invoice_number, invoice_date, relation_text (the literal phrase), stated_relation}. `stated_relation` is credits, corrects, replaces, cancels, refers_to or unknown.
- `currency_raw`, `supplier_contact_person`.
- `recipient_name`, `recipient_vat_number` (needed by E4 and A8), `recipient_contact_person` (the "t.a.v." line).
- `references`: every printed reference with its literal label. Code decides which ones are PO numbers.
- `payment_terms_raw`, and `vat_breakdown` as a list of {rate_raw, base_raw, vat_raw}.

New line fields:
- `employee_name`, `work_date`, `order_reference_raw`.
- `rate_type_raw`: the literal shift or surcharge text (dag, avond, nacht, weekend, feestdag, toeslag).
- `vat_rate_raw`.
- `location` is re-described as "Object, locatie or project as printed".

Not extracted: phone numbers, email addresses and personal IDs. A test asserts the schema has no field that looks like a phone number.

**Prompt v2.** New rules 8 to 14:
- the document type as declared, with signs as printed;
- referenced invoices copied literally, never inferring a relation from amounts;
- every reference with its label, without deciding which is a PO;
- the issuer's contact person, and the recipient's name, btw-id and "t.a.v.";
- payment terms copied literally, and `due_date` only if printed, never computed (code computes it as a "calculado" value);
- for each line: employee, Object, dates, reference and rate type;
- `low_confidence_fields` uses paths such as `lines[3].location`;
- any text asking to call a number, confirm bank details or update the supplier file goes into `document_notes`.

The wording becomes neutral about direction ("documents where BM Support BV is the issuer or the recipient"). Rule 1 stays word for word.

**Parsing and compatibility**
- `parse_importe` returns the amount and its currency, so any non-EUR currency raises X1.
- `es_unidad_hora`, `parse_plazo_pago` and `normalizar_referencia` are added.
- `compat.py` upcasts v1 records when they are read and never rewrites them. Fields that only v2 asks for are marked "faltante: no solicitado en v1", never "not on the document". Rules that need them return `sin_datos`. On v1 records, X1 falls back to scanning the amount literals with `detectar_moneda`.

**Cache and cost**
- **Default policy CONSERVAR:** any stored extraction of the same bytes is reused, whatever version made it. `extract --estricta` keeps today's behaviour for measurements, and `--force` is unchanged.
- **No overwrites:** extractions are added, never overwritten. The `out/` JSON becomes an export named by hash and versions.
- **Budgeted re-extraction:** `reextraer --abiertas|--desde|--proveedor|--sin-objeto --limite --presupuesto [--lote] [--activar]`.
  - Input tokens are counted exactly with `count_tokens`, schema included.
  - Output tokens are estimated from v2 history. Until there are 3 v2 documents, it uses the v1 median times a declared factor, labelled "sin medir".
  - It refuses to run when the high estimate exceeds the budget.
- **Activation gate:** `--activar` makes the new extraction current only after `score --comparar-versiones` shows v2 at least as good as v1 and at least 98% on the critical fields of the real set, with the injection PDF still yielding the header IBAN.
  - On activation, every manual value the new extraction contradicts raises M1.
  - Manual line edits are re-mapped by each line's fingerprint; edits that can't be mapped become findings.
- **History can stay v1.** Closed and paid history doesn't need re-extraction; a person can fill in missing fields by hand.

**Batch path**
- `construir_peticion_lote(doc)` uses `output_config.format` json_schema and carries no tools, `tool_choice` or `mcp_servers`.
- `custom_id` is the document's sha256, because batch results arrive in any order.
- Results are validated with `model_validate_json`. Refusals, errors and expired requests go to a retry list, because Batches don't accept server-side fallbacks.
- Batches cost 50% of the normal price. D3 estimates the v2 run at about $6–7 per 100 documents synchronous and $3–3.5 batched, which is consistent with the verified prices.

**Model choice**
- Add claude-opus-5-5 ($4 in, $20 out) to `pricing.py`.
- If the model changes, do it in the same pass as the schema bump so the documents are paid for once.
- Set `effort` explicitly: Opus 5.5 defaults to medium, and its thinking cannot be turned off. Re-score afterwards. The choice is decided by measurement, as fase-0 already does.

**Scoring and ground truth**
- `_FIELD_SOURCE` gains `document_type`, `currency_raw`, `references`, `related_invoices`, `recipient_vat_number` and the contact fields. Lists are compared as normalised sets.
- `CRITICAL_FIELDS` is unchanged, so the 98% gate stays comparable.
- The sample generator adds a credit note and a USD invoice. `03-con-inyeccion.pdf` remains the end-to-end F2/F3/Q3 test.

**Outgoing PDFs.** They are read only when no structured source exists. The direction comes from the intake route (`ruta_declarada`), never from the model.

---

## 11. Build order

Each step ships with a gate that must pass before the next one starts.

**Step 0. Baseline and defect fixes** (no store, no API spend)

Work:
- Install the dev dependencies (`pip install -e '.[dev]'`).
- Add v1 fixtures: the 3 sample invoices, a credit note, a line in "uren", a dd-mm-yyyy date, the injection invoice and a USD invoice.
- Take a golden snapshot of `construir_datos`.
- Apply every code fix:
  - `es_unidad_hora` in the dashboard and the projection;
  - `detectar_moneda`, so a non-EUR literal is flagged instead of stripped;
  - B4 becomes "revisar";
  - the E3 label;
  - G3 grouped by provider identity;
  - `detectar_ibanes` stops naming the oldest document IBAN as the reference;
  - the claude-opus-5-5 pricing row.
- Harden `serve.py`: exact Origin match (closes the prefix bypass), a Host allowlist, an `X-BMS-Token` header, and JSON-only POST.
- Make `write_json` never overwrite an extraction made under other versions, and make CONSERVAR the default.

Gate:
- All 125 existing tests pass, and the golden snapshot is equal except for the documented fixtures.
- A cross-origin form POST gets 403, and a foreign Host gets 403 or 421.
- The Origin `http://localhost.attacker.example` gets no CORS header.
- A fake client makes 0 calls when only the version changed.

**Step 1. Store, evidence and audit, with a zero-API migration**

Work:
- `almacen/`, migration 0001 (migracion, politica_version, users and permissions, evento, cambio_campo, documento, extraccion, importacion).
- The document store, `auditoria.py`, `unidades.py`, `db init|verificar`, `importar-out`, `registros_legado()`.
- `extract` and `serve` write to both the store and `out/`.

Gate:
- UPDATE and DELETE abort on every append-only table.
- The chain verifier catches a row edited through a raw connection after the triggers were dropped.
- The document store refuses overwrites and detects a hash mismatch.
- Running `importar-out` twice gives the same row counts, and the stored payloads are byte-identical to the files.
- A missing PDF leaves `ruta_cas` NULL.
- The anthropic import is patched to raise, proving zero API calls.
- `construir_datos(registros_legado(db))` equals `construir_datos(load_records(out))`.

**Step 2. Typed core, single write path, provenance, permissions**

Work:
- Migration 0002: master data (without bank accounts), factura, factura_linea, factura_imputacion, factura_iva, factura_referencia, factura_relacion, procedencia_campo, nota, plus the guard triggers.
- `campos.py`, `permisos.py`, `identidad.py`, `compat.py`, `ingesta.py`, `registros_resueltos()`.
- Seed Objects, clients and sale rates from `config/tarifas.yaml`, so Object allocation works early.
- The panel, report and export read from the store.

Gate:
- The original value survives two corrections.
- The system, not the user, decides between "supplemented" and "corrected", and a revert restores the original source.
- An automatic value never overwrites a manual one.
- A correction without a reason is refused.
- An UPDATE outside `campos.py` is rejected by the guard, and a grep test finds none in the code.
- The golden snapshot is unchanged through `registros_resueltos`.

**Step 3. Rule engine and findings**

Work:
- Migration 0003 (control tables).
- `reglas/` base, catalogue and engine. Port Q1, D1–D4, D2b, E3/E4 and F1 from `checks.py`, and B2, B3, B4 and history-based G3 from `dashboard.py`; both files delegate to the new modules.
- `hallazgos.py` and the daily `recalcular`.

Gate:
- The AST purity test and the recording-proxy test pass.
- Shuffled input gives identical fingerprints, and recomputing twice creates no duplicates.
- A sticky finding never closes itself, and an override stops applying once the fingerprint changes.
- The old tests stay green through the wrappers.
- 5.000 invoices recompute in under 2 seconds.

**Step 4. Exceptions, review, priority, commands, console**

Work:
- `excepciones.py`, `revision.py`, `prioridad.py`.
- `servicios.py` with the §10 commands, the CLI, `POST /api/v2/acciones` and a minimal console.
- The scope suite starts running from here.

Gate:
- Each command writes its rows, audit and recompute in one transaction.
- A correction that fixes D4 closes it with its cause recorded, and leaves the edit unresolved until it is verified.
- Any later change invalidates a review.
- Table-driven priority tests: every floor, every threshold edge, the needs-action gate, the waiting-external rules, and raise-only.
- A permission matrix test; system actors are refused for every human command.
- A console XSS test: document text containing `<script>` renders as text.

**Step 5. Master data and the IBAN registry**

Work:
- Migration 0004: cuenta_bancaria, cuenta_evento, beneficiario_conocido, tarifa_acordada, ciclo_facturacion.
- The importer framework and the Exact or CSV master-data mappings.
- Baseline, attestation and verification commands.
- Rules A0, A2, A5, A7, A8, F2–F6, F8, F9, E1, E2, U1, Q2–Q4, X1, Z1 and Z2.

Gate:
- A property test shows that no extraction, including `03-con-inyeccion`, ever creates or changes a `cuenta_bancaria` row.
- The injection fixture is Blocked by F2/F3 and also raises Q3.
- An IBAN change in a later Exact batch is Blocked by F5 and stays open after the next import.
- A verification made with a phone number changed 3 days earlier is ineffective (F8).
- The importer cannot write a `verificada` state.
- Each mapping has its contract test, and re-importing a file does nothing.

**Step 6. Extraction v2** (the only step that spends API money, and it only runs when started on purpose)

Work:
- Schema and prompt v2, the upcast, the new parsing functions, the scoring changes, the cost estimate per schema version, `reextraer` and the batch builder. Then bump the versions.

Gate:
- Automatic checks:
  - every schema object has required equal to its properties and `additionalProperties:false`, with no unsupported keyword;
  - there is no phone field and no tools;
  - the v1 fixtures upcast with exactly the new keys marked "no solicitados".
- Manual checks before `--activar`:
  - the cost estimate is within budget;
  - v2 is at least as good as v1, and at least 98% on the critical fields of the real set;
  - the injection PDF still yields the header IBAN, with the injected text in `document_notes`.

**Step 7. Bank, payments, cash flow**

Work:
- Migration 0005 (bank statements, movements, payment applications).
- CAMT.053 and MT940 parsers and bank CSV presets; `pagos.py`.
- The Exact open-items importer and `flujo_caja.py`.
- Rules K1–K8 and F7.

Gate:
- CAMT .001.02 and .001.08 fixtures, including batched TxDtls.
- A DOCTYPE is rejected, a foreign own account is rejected, and a non-EUR row gives X1.
- A continuity break blocks (K6), and a double debit gives K4.
- A partial payment stays Outstanding with its balance and K2; a payment made while Blocked gives K5.
- Cash-flow buckets are tested with a fixed date across Sunday to Monday and month end.

**Step 8. Outgoing invoices, relationships, provider and client overviews**

Work:
- The Exact sales mapping and the outgoing PDF route.
- `relaciones.py` proposals and the confirmation commands.
- Rules R1–R5, V7 and F10, plus the arithmetic rules as holds on outgoing invoices.
- Overviews §3 and §4.

Gate:
- The route decides the direction, and a misrouted outgoing document is Blocked.
- A full credit note marks the original Credited; a partial one reduces its balance.
- Replaced or corrected invoices are excluded from totals, cash and VAT.
- B4 is not raised for a confirmed pair.
- A mismatch between Exact and the PDF is a discrepancy.

**Step 9. Purchase orders and agreed rates**

Work:
- Migration 0006 (purchase orders and their amendments).
- PO import and commands, `ordenes_compra.py`, rules P1–P10.
- G3 and V4 against the agreed rates, keeping the history fallback.

Gate:
- Consumption arithmetic: excluding VAT, credits subtracted, cancelled and replaced invoices left out.
- P4 respects the ordering; thresholds come from config.
- Expiry is tested with a fixed date, and the forecast is deterministic.

**Step 10. Planning** (the mapping is built now against a synthetic fixture and switched on when a real export arrives)

Work:
- Migration 0007 (planning shifts and reconciliation), `conciliacion.py`.
- Rules G1–G7, V1–V6, V8, V9, the planning part of B5, and the planned-work inputs of P8 and P10.
- Object overview hours (§5).

Gate:
- The comparison picks the right level (day, week or period).
- The ISO-year boundary works (an invoice dated 6 January for week 52).
- Tolerance edges: 0,25 h passes and 0,26 h fails.
- Cancelled shifts are ignored, and unbilled work appears only after the period end plus the grace days.
- A night surcharge at its agreed rate gives no G3, and a newer batch that changes a billed week gives V9.

**Step 11. BTW**

Work:
- Migration 0008 (BTW periods), `config/btw.yaml` (confirmed with the accountant).
- Self-assessed reverse charge, `btw.py` and the status commands.
- Rules C4, E0 and E7.

Gate:
- 21% standard VAT.
- Reverse-charged incoming invoices appear in rubric 2a and 5b and net to zero.
- KOR, and a credit note in a later quarter.
- The Q4 deadline is 31 January, and the Q3-2026 deadline is 2026-10-31.
- Filing is irreversible and hashed, and a late invoice in a filed quarter gives C4.

**Step 12. Dashboard, search, contract v2, docs**

Work:
- The §17 blocks and §18 filters in `consultas.py`.
- `/api/v2` and `export --v2`.
- Console pages with provenance and manual-edit badges.
- The docs.

Gate:
- Consistency properties: a provider's outstanding total equals the sum of its outstanding invoices, and Object revenue plus unallocated revenue equals the total outgoing base.
- One test per §18 filter.
- The legacy `/api/datos` is still byte-identical to the golden snapshot.

**The scope suite runs from step 4 onward.** It checks that:
- no command or state creates or drafts an invoice, pays, approves a payment or files BTW;
- there is no SEPA or pain.001 generator, and no bank credential or config key;
- no entity models instalment plans;
- non-EUR is always Blocked;
- no code path leads from an extraction to `cuenta_bancaria` (import graph and property test);
- extraction and batch requests carry no tools.

---

## 12. Questions for the product owner that change the design

1. **IBAN baseline and four-eyes.** Does the first Exact import count as the reference (flagged as unverified), or should nothing get "sin objeciones" until it is attested or called back? Is there a second person for four-eyes review, and above what amount?
2. **Payment data.** Which bank or banks, which format (CAMT.053 is preferred), and how often is it exported? Is Exact's payment status used too, and which source wins? Is there any tolerance for bank costs?
3. **TRNSPRNT.**
   - Is there an API, or only exports?
   - Does each shift carry a stable ID, approved hours and the provider?
   - Which rates does it hold?
   - What share of purchase invoices does it self-bill? If the share is high, step 6's spend should be reconsidered.
4. **Outgoing invoices.** Do they come from Exact or from TRNSPRNT? Do their lines carry Object, resource and work period? How many Exact administrations (divisions) are there?
5. **Purchase orders.** Who issues them to whom? Are values excluding VAT? Which clients or Objects require one, and who maintains the list?
6. **Rates and billing cycles.** Where do agreed rates come from, and are surcharges separate rates or percentages? What is the billing cycle and the grace period per client or Object?
7. **Thresholds and weights.** U1, the PO warning percentage and expiry window, the priority tiers, the G3 rate excess that blocks instead of holds, the freshness limits and the phone cool-down.
8. **VAT, for the accountant.** Does reverse charge apply to BMS's work? What is the rubric mapping? Factuurstelsel or kasstelsel, quarterly filing, and how are invoices that arrive after a quarter is filed treated?
9. **Users and roles.**
   - Who holds which permission?
   - Is attribution by local token acceptable for V1, until Entra ID comes with deployment?
   - Should `revisar_factura`, `gestionar_btw` and `importar_datos` be added to §19?
10. **Attribution and reasons.** Are Object margins and YTD figures attributed by work period or by invoice date? Is a reason mandatory for every manual edit, or only for corrections?