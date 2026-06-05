# payroll — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_payroll/{models.py,services.py,calculation.py,invariants.py,collectors/*}`.
El CRUD plano (alta de nómina en borrador, alta de concepto, upsert de ajustes) y las
lecturas ya están en SQL declarativo Tier 0 (`commands/*.sql`, `queries/*.sql`). Lo que
sigue es lógica de cálculo / batch / agregación cross-módulo / invariantes que **no** cabe
en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (vía queries públicas / capacidades de host), calcula y devuelve *intenciones*
> (filas a insertar/actualizar, comandos a ejecutar) que el runtime valida y persiste en
> una transacción. Todos los importes se redondean con `quantize(0.01)`.
>
> ⚠️ payroll es **compliance-critical** (RDL 8/2019 español): según `ARQUITECTURA.md` §5.3
> el escape-hatch admitido es **plugin nativo de primera parte estáticamente enlazado** en
> lugar de WASM Extism si la lógica fiscal lo requiere. Documentado aquí como handler; la
> decisión WASM-vs-nativo se toma al implementar.

---

## 1. `calculate_payslip`  (command `payroll.calculate`)
Origen: `calculation.py::PayrollCalculationService.calculate` + `.confirm`.
Payload: `{employee_id, period_start, period_end, confirm: bool}`.

Es el corazón del módulo. Orquesta **colectores** y calcula bruto/deducciones/neto.

### 1.1 Datos que el runtime debe leer y pasar al handler (cross-módulo = SOLO contrato)
payroll **depende de `staff`** y opcionalmente lee de `time_control`, `timesheets`,
`commissions`. PROHIBIDO `SELECT` directo a sus tablas. El runtime debe exponer estos datos
vía **queries públicas de cada módulo** (o eventos) y pasarlos al handler como entrada:

- `staff` (dependencia dura): empleado `{id, full_name, hourly_rate}`. Si no existe → error
  `employee_not_found`.
- `payroll.settings.get` (propia): `overtime_multiplier`, `income_tax_rate`,
  `social_security_rate`, `auto_calculate_deductions`. Defaults si no hay fila:
  `1.50 / 15.00 / 6.35 / true`.
- `time_control` (opcional): query pública que devuelva las `DailySummary` del periodo →
  horas BASE + OVERTIME. **Autoritativo** (RDL 8/2019). Si el módulo no está instalado → vacío.
- `timesheets` (opcional): query pública de `TimeEntry` con `status='approved'` y
  `billable=true` del periodo → línea BASE complementaria. Solo se usa si `time_control`
  no devolvió nada.
- `commissions` (opcional): query pública de `CommissionPayout` con
  `payment_method='payroll'`, `status IN ('approved','pending')` y periodo solapado →
  líneas COMMISSION. Siempre se añaden.

### 1.2 Precedencia de colectores (orden exacto del legacy)
1. `time_control` — autoritativo: produce BASE + OVERTIME.
2. `timesheets` — complementario: **solo** si `time_control` no produjo líneas.
3. `contract` (fallback) — **solo** si ninguno de los anteriores produjo BASE:
   `amount = quantize(hourly_rate * 160, 0.01)` (160 h = jornada completa mensual estándar).
4. `commissions` — **siempre** se añaden, independientes de las horas.

`base_lines = time_control || timesheets || contract`; `all_lines = base_lines + commission_lines`.

### 1.3 Cálculo del bruto (`gross`)
`gross = quantize(Σ amount de líneas con type ∈ {BASE, OVERTIME, COMMISSION, OTHER}, 0.01)`.

### 1.4 Cálculo de deducciones automáticas
Solo si `settings.auto_calculate_deductions` y `gross > 0`:
- Seguridad Social (empleado): `ss = quantize(gross * social_security_rate / 100, 0.01)`,
  concepto `"Social Security (employee)"`, notes `"{rate}% of gross"`.
- IRPF: `it = quantize(gross * income_tax_rate / 100, 0.01)`,
  concepto `"Income Tax (IRPF)"`, notes `"{rate}% of gross"`.
- `total_deductions = quantize(Σ deducciones, 0.01)`; `net = quantize(gross - total_deductions, 0.01)`.

### 1.5 Modo borrador vs confirmar
- `confirm = false` → devolver el **draft** sin persistir:
  `{employee_id, employee_name, period_start, period_end, gross, deductions, net, lines:[...]}`.
- `confirm = true` → emitir intenciones de inserción:
  - Cabecera `payroll_payslip`: `gross_salary=gross`, `total_earnings=gross`,
    `total_deductions`, `net_salary=net`, `status='draft'`.
  - Por cada línea (con `sort_order = índice`): insertar `payroll_payslip_line` con
    `type = 'deduction'` si la línea era DEDUCTION, si no `'earning'`; copiar
    `concept_name, amount, quantity, rate, source_module, source_id`.
  - **Cross-módulo (evento, NO import)**: por cada línea con `source_module='commissions'` y
    `source_id`, marcar ese payout como incluido. En hub-next NO se hace
    `payout.mark_included_in_payslip(...)` directo → emitir evento
    `payroll.payslip.created` con `{commission_payout_ids:[...]}` y que `commissions` lo
    consuma vía su propio listener. El legacy lo hacía con import directo; aquí se rompe esa
    dependencia.
  - Devolver `{id, employee_name, gross, net, lines_count}`.

---

## 2. `approve_payslip`  (command `payroll.payslips.approve`)
Origen: `services.py::PayslipService.approve_payslip` (risk_tier=3, financial_impact)
+ invariante `payroll.totals_balance` (`invariants.py`).
Payload: `{payslip_id}`.

- Guardas de estado: si `status == 'approved'` → error `already_approved`; si
  `status == 'paid'` → error `cannot_approve_paid`. En otro caso → `status = 'approved'`.
- **Invariante `payroll.totals_balance` (DEBE ejecutarse dentro de la transacción antes de
  commit)**: leer la nómina aprobada + sus líneas; `earnings = Σ amount(type='earning')`,
  `deductions = Σ amount(type='deduction')`; `net_expected = gross + earnings - deductions`;
  si `|net_expected - net_stored| > 0.01` (un céntimo de tolerancia) → **Violation** y
  rollback. Si la fila no aparece tras la acción → también Violation.
- Devolver `{success:true, payslip_id, status:'approved'}`.

> Va a handler (no a un simple `UPDATE`) por: (a) guardas de transición de estado, (b) el
> invariante de balance que requiere releer líneas y agregarlas dentro del SAVEPOINT.

---

## 3. `delete_payslip`  (command `payroll.payslips.delete`)
Origen: `services.py::PayslipService.delete_payslip` (risk_tier=2).
Payload: `{payslip_id}`.

- Guarda fiscal/auditoría: si `status == 'paid'` → error `cannot_delete_paid` (las nóminas
  pagadas no se borran nunca).
- En otro caso → **soft-delete**: `is_deleted=1`, `deleted_at=:now`, `updated_by`, `updated_at`
  en `payroll_payslip` **y** en sus `payroll_payslip_line` (cascada lógica).
- Devolver `{success:true, deleted:payslip_id}`.

> Va a handler por la guarda condicional de estado + el soft-delete en cascada de las líneas
> (dos tablas), que no es un único `DELETE`/`UPDATE` trivial.

---

## 4. `get_stats` (reporte, `view_reports`) — PENDIENTE de portar
Origen: `services.py::PayslipService.get_stats`.
Estadísticas de nómina por periodo: `payslip_count`, `total_gross`, `total_net`,
`total_deductions`, `average_gross`, `average_net`, desglose `by_status`.
- Las sumas/contadores se pueden resolver como **query agregada** (SUM/COUNT/GROUP BY) sin
  WASM; las medias (`total/count`) y el armado del dict `by_status` los puede componer el SDK
  o un handler ligero. No incluido como query/command todavía porque no hay vista `dashboard`
  implementada (sin entrada de nav muerta). Portar cuando se añada la vista de reportes.

---

## 5. Listener de evento `staff.member_updated`
Origen: `events.py::_on_staff_member_updated`.
Hoy el legacy solo **loguea** (no muta nada). Declarado en `module.json` (`events.listen`).
Si en el futuro debe ajustar nóminas futuras al cambiar el salario de un empleado, esa
lógica iría a un handler; por ahora es no-op de trazabilidad. No bloqueante.

---

## 6. Notas de redondeo / tipos
- Todos los multiplicadores (`overtime/night_shift/holiday`) y tipos (`social_security_rate`,
  `income_tax_rate`) son porcentajes decimales; aplicar siempre `quantize(0.01)` al final.
- `night_shift_multiplier` y `holiday_multiplier` existen en settings pero el legacy
  `calculate()` solo usa `overtime_multiplier` en el colector `time_control`. Conservados en
  el esquema para cuando el colector de horas distinga turnos noche/festivo.
