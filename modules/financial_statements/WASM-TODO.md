# financial_statements — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_financial_statements/{models.py,services.py}`. El CRUD plano
(crear plantilla, añadir línea, finalizar informe) ya está en SQL declarativo Tier 0
(`commands/{template_create,line_item_add,report_finalize}.sql`). Lo que sigue es lógica de
cálculo / agregación / diff que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el runtime
> ha leído (plantilla + sus line_items, o los snapshots `data` de los informes), calcula y
> devuelve *intenciones* (fila a insertar en `financial_statements_generated`, o un dict de
> respuesta de solo-lectura para export/compare) que el runtime valida y persiste en una
> transacción. Todos los importes se manejan con `quantize(0.01)` (2 decimales).

## Helpers compartidos (de services.py)
- `_parse_iso_date(value)`: acepta `None`/`""`/`YYYY-MM-DD`/`date`/`datetime` → `date|None`.
- `_to_decimal(value, default="0")`: str/Decimal/float/int → `Decimal`.
- `_normalize_balances(map)`: `{code: value}` → `{str(code): Decimal(value)}`.
- `_group_lines_by_section(line_items)`: agrupa preservando el orden de primera aparición
  (las líneas ya vienen ordenadas por `item_order`).
- `_compute_line_value(line, balances)`: `sign * Σ balances[code]` sobre `account_codes`,
  `quantize(0.01)`.
- `_build_report_data(template, line_items, balances)`: núcleo de render del snapshot — ver §4.

## 1. `generate_balance_sheet`  (command `financial_statements.reports.generate_balance_sheet`)
Origen: `FinancialReportService.generate_balance_sheet` + `_generate_with_template`.
- Binds que el runtime debe leer y pasar al WASM: la plantilla (`templates.get`) y sus líneas
  (`templates.lines`) para `template_id`.
- Validar fecha: `as_of = _parse_iso_date(as_of_date)` (error `invalid_date` si falla).
- Guard de tipo: `template.report_type` debe ser `balance_sheet` **o** `custom`; si no →
  error `report_type_mismatch`.
- Validar `account_balances` es dict no nulo → si no, error `missing_balances`.
- `balances = _normalize_balances(account_balances)`.
- Construir `data = _build_report_data(template, line_items, balances)` (§4).
- Intención de inserción en `financial_statements_generated`:
  `report_type='balance_sheet'`, `period_start = period_end = as_of`, `generated_at = now`,
  `status='draft'`, `data = <snapshot>`, `notes`. El runtime inyecta id/hub_id/auditoría.
- Emitir `financial_statements.report.generated`.
- Devolver `{id, template_id, report_type, status, total, data}`.

## 2. `generate_profit_loss`  (command `financial_statements.reports.generate_profit_loss`)
Origen: `FinancialReportService.generate_profit_loss`.
- Igual que §1 pero `expected_type='profit_loss'`, con `period_start`/`period_end`
  parseados por separado (ambos `_parse_iso_date`, error `invalid_date`).

## 3. `generate_cash_flow`  (command `financial_statements.reports.generate_cash_flow`)
Origen: `FinancialReportService.generate_cash_flow`.
- Igual que §2 pero `expected_type='cash_flow'` y el mapa de entrada se llama `cash_movements`
  (se trata idéntico a `account_balances`: las líneas de la plantilla etiquetan los
  movimientos operating/investing/financing).

## 4. Núcleo de render del snapshot (`_build_report_data`)
Origen: `_build_report_data` + `_compute_line_value`. Es la lógica central de los tres
generadores y debe vivir en el WASM:
- Agrupar líneas por sección preservando orden (`_group_lines_by_section`).
- Por sección, recorrer las líneas en orden:
  - Línea `is_total=1` → su `value = running_total` de la sección hasta ese punto
    (no añade nada nuevo; es subtotal acumulado).
  - Línea normal → `value = _compute_line_value(line, balances)` = `sign * Σ balances[code]`;
    acumular en `running_total` y `section_subtotal`.
  - Emitir `{code, label, value (str), is_total, sign}`.
- `section.subtotal = quantize(section_subtotal, 0.01)`; `grand_total += section_subtotal`.
- Salida:
  `{template_id, template_code, template_name, report_type, structure, sections:[...], total}`.
- Todos los valores numéricos serializados como string (`str(Decimal)`), con `quantize(0.01)`.

## 5. `export_report`  (command `financial_statements.reports.export`)
Origen: `FinancialReportService.export_report`. Solo-lectura (no persiste): el runtime lee el
informe (`reports.get`) y pasa su `data` snapshot al WASM, que compone:
- Solo `format='json'` soportado (error `invalid_format` en otro caso).
- `header`: `{report_id, report_type, template_id, template_code, template_name,
  period_start, period_end, status, generated_at, notes}` (codes/names salen del snapshot).
- `lines`: lista plana derivada de `sections[].lines[]` →
  `{section, code, label, value, is_total}` (útil para export a hoja de cálculo).
- `totals`: `{total, by_section: {section_id: subtotal}}`.
- Devolver `{format:'json', header, sections, lines, totals}`.
- NOTA: cuando se quiera export a Excel/PDF real, usar capacidad de host Tier 1
  (PDF/Excel render) en vez de devolver JSON.

## 6. `compare_reports`  (command `financial_statements.reports.compare`)
Origen: `FinancialReportService.compare_reports`. Solo-lectura: el runtime lee ambos informes
(`reports.get` × 2) y pasa sus snapshots `data` al WASM, que calcula el diff:
- Indexar cada informe por `(section_id, line.code)` → línea.
- Para cada clave en A: si no está en B → `status='only_in_a'` (value_b/delta = null);
  si está → `delta = quantize(value_b - value_a, 0.01)`, `status='changed'|'unchanged'`.
- Para cada clave solo en B → `status='only_in_b'` (value_a/delta = null).
- `totals`: `{total_a, total_b, delta = quantize(total_b - total_a, 0.01)}`.
- Devolver `{report_a, report_b, totals, diff:[...]}`.
- Cross-module: este módulo NO depende de un plan de cuentas. Los `account_balances` /
  `cash_movements` los aporta el llamador (m_accounting, import, entrada manual) vía el payload
  del comando — nunca leemos tablas de otro módulo (DEPENDENCIES = [] en el legacy).
