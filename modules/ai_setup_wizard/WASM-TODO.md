# ai_setup_wizard — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_ai_setup_wizard/{models.py,services.py}`. El CRUD plano
(responder una pregunta, dar de alta una recomendación) ya está en SQL declarativo
Tier 0 (`commands/question_answer.sql`, `commands/recommendation_add.sql`). Lo que sigue
es lógica de autonumeración / guardas de estado / mutación de listas JSON que **no** cabe
en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. La marca de tiempo (`:now`) y el contador atómico
> son capacidades del host (reloj, counter UPSERT), no las inventa el WASM.

## 1. `start_session`  (command `ai_setup_wizard.sessions.start`)
Origen: `SetupWizardService.start_session` + `_generate_session_number`.
- Validar: `business_type` no vacío; `team_size` entero ≥ 1 (el JSON Schema ya acota, pero
  el handler revalida y devuelve `invalid_team_size` / `missing_business_type` si falla).
- Generar `session_number` atómico → ver pieza 6 (counter).
- Insertar la cabecera con `status='active'`, `started_at = :now`, `goals=[]`, `pain_points=[]`,
  `recommended_modules=[]`, `applied_modules=[]`, `user_ref` = usuario activo (lo aporta el runtime).
- Devolver `{id, session_number, business_type, status}` y emitir `ai_setup_wizard.session.started`.

## 2. `complete_session`  (command `ai_setup_wizard.sessions.complete`)
Origen: `SetupWizardService.complete_session`.
- Leer la sesión por `session_id` (runtime); si no existe → `not_found`.
- Guarda de estado: si `status == 'completed'` → error `already_completed`.
- Set `status='completed'`, `completed_at = :now`. Si llega `recommended_modules` (lista no nula),
  reemplazar el JSON `recommended_modules` por esa lista (serializar a JSON array de strings).
- Devolver `{id, session_number, status, recommended_modules}` y emitir
  `ai_setup_wizard.session.completed`.

## 3. `abandon_session`  (command `ai_setup_wizard.sessions.abandon`)
Origen: `SetupWizardService.abandon_session`.
- Leer la sesión; si no existe → `not_found`.
- Guardas de estado: `completed` → error `completed_locked`; `abandoned` → error `already_abandoned`.
- Set `status='abandoned'`. Si llega `reason`, **append** al campo `notes` con prefijo:
  `notes = (notes + "\n" if notes) + "[ABANDONED] " + reason` (trim final). Append textual con
  el `notes` actual leído por el runtime → no es una sola UPDATE idempotente.
- Devolver `{id, session_number, status}` y emitir `ai_setup_wizard.session.abandoned`.

## 4. `add_question`  (command `ai_setup_wizard.questions.add`)
Origen: `SetupWizardService.add_question`.
- Validar `question_text` no vacío y `question_type ∈ {text,single_choice,multi_choice,scale}`
  (JSON Schema lo cubre; el handler revalida → `missing_question` / `invalid_type`).
- Leer la sesión; si no existe → `not_found`. Guarda de estado: **solo** si `status == 'active'`
  (si no → error `invalid_state`, "Cannot add questions to a {status} session").
- Calcular `question_order` = (nº de preguntas existentes de la sesión leído por el runtime) + 1.
  Es 1-based y depende de un COUNT previo → no cabe en un único INSERT determinista sin carrera.
- Insertar la pregunta con `options` serializado a JSON array, `answer=''`.
- Devolver `{id, session_id, question_order, question_type}` y emitir
  `ai_setup_wizard.question.added`.

## 5. `apply_recommendation`  (command `ai_setup_wizard.recommendations.apply`)
Origen: `SetupWizardService.apply_recommendation`. **Multi-fila + mutación de lista JSON.**
- Leer la recomendación por `recommendation_id` (runtime); si no existe → `not_found`.
- Guarda: si `is_applied` ya es true → error `already_applied`.
- Leer la sesión padre (`session_id` de la recomendación); si no existe → `not_found`.
- Marcar la recomendación: `is_applied=1`, `applied_at = :now`.
- Si la recomendación trae `related_module_id` no vacío: leer `applied_modules` (JSON array) de la
  sesión, y si el id **no** está ya presente, hacer append y persistir el nuevo JSON en la sesión.
  Esta lectura-modificación-escritura de un array JSON sobre dos tablas (recommendation + session)
  es la razón por la que va a WASM (dos UPDATEs coordinados + dedupe de lista).
- Devolver `{id, session_id, is_applied, applied_at, applied_modules}` y emitir
  `ai_setup_wizard.recommendation.applied`.

## 6. Contador atómico de nº de sesión (`_generate_session_number`)
Origen: `SetupWizardService._generate_session_number`. Formato `SET-YYYYMMDD-NNNN`
(NNNN = secuencia por hub+día, 4 dígitos, 1-based).
- El legacy lo deriva con un COUNT de `session_number LIKE 'SET-YYYYMMDD-%'`, lo que tiene
  ventana de carrera. En hub-next se resuelve como **capacidad del runtime** (counter UPSERT
  atómico por clave `hub_id + día`), invocada por el handler; el WASM solo formatea
  `SET-{YYYYMMDD}-{n:04d}` con el número devuelto. El día sale del reloj del host (`:now`).

## 7. `get_summary`  (reporte — pendiente de exponer)
Origen: `SetupWizardService.get_summary`. Agregado de completitud:
- `total_questions`, `answered_questions` (con `answered_at` no nulo),
  `completion_percent = round(answered/total*100, 1)` (0 si no hay preguntas).
- `total_recommendations`, `applied_recommendations` (con `is_applied`).
- Devuelve también `applied_modules` / `recommended_modules` (JSON arrays) de la cabecera.
- Es un cálculo agregado sobre 2 tablas; **no** se ha expuesto como query SQL Tier 0 porque
  mezcla agregados de preguntas y recomendaciones + un porcentaje redondeado. Cuando se necesite,
  se implementa como handler WASM de solo-lectura (recibe los recuentos del runtime y formatea el
  resultado) o como dos queries + cálculo en la UI. No bloqueante para el CRUD principal.
