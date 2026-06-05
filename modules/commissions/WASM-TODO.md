# commissions — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_commissions/{models.py,services.py,routes.py,events.py}`.
El CRUD plano y las transiciones de estado simples ya están en SQL declarativo Tier 0
(`commands/*.sql`: rule create/update/delete, transaction approve, payout approve,
adjustment create/delete, settings upsert). Lo que sigue es lógica de **cálculo /
agregación batch / atomicidad / cascada** que **no** cabe en una sola sentencia SQL y
debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas leídas por el
> runtime (queries que el host ejecuta y le pasa), calcula y devuelve *intenciones* (filas a
> insertar/actualizar + comandos a ejecutar) que el runtime valida y persiste en una sola
> transacción. Todos los importes se redondean con `quantize(0.01, ROUND_HALF_UP)` igual que
> el legacy (`Decimal`). El handler nunca filtra `hub_id` a mano — lo inyecta el runtime.

---

## 1. `calculate_commission`  (command `commissions.calculate`)
Origen: `CommissionRule.calculate_commission` (models.py).
Función de **solo lectura/preview** (no muta): calcula cuánta comisión generaría una regla
para un importe dado. El runtime lee la regla (`commissions.rules.get`) y se la pasa al WASM.

Payload: `{amount, rule_id, sales_volume?}`. Lógica según `rule.rule_type`:
- `flat`     → `commission = rule.rate` (importe fijo, ignora `amount`).
- `percentage` → `commission = quantize(amount * rule.rate / 100, 0.01)`.
- `tiered`   → requiere `rule.tier_thresholds` (JSON `[{min_amount,max_amount,rate}]`) y
  `sales_volume`. Ordenar tramos por `min_amount` asc; elegir el tramo cuyo rango
  `[min_amount, max_amount]` contiene `sales_volume` (si `max_amount` es null → tramo abierto
  superior, basta `sales_volume >= min_amount`). Resultado:
  `commission = quantize(amount * tier.rate / 100, 0.01)`. Sin tramo aplicable o sin
  `sales_volume` → `0`.
Devolver `{commission_amount, rule_type, rate_applied}`.

## 2. `accrue_from_sale`  (command `commissions.transactions.accrue_from_sale`, listener de `sales.completed`)
Origen: `events.py::_on_sale_completed`. Cross-módulo **por evento, no por import**: `commissions`
escucha `sales.completed` (declarado en `module.json::events.listen`) y nunca importa de `sales`.

Datos que el runtime debe aportar al WASM (leídos vía queries propias y del payload del evento):
- Del payload del evento: `sale_id`, `sale_reference`, `sale_total`, `staff_id`, `staff_name`,
  `appointment_id`, `transaction_date` (si null → hoy).
- De BD (queries propias del módulo, ejecutadas por el host):
  - `commissions.settings.get` → `apply_tax_withholding`, `tax_withholding_rate`.
  - `commissions.rules.list (only_active='1')` → todas las reglas activas ordenadas por
    `priority DESC`.

Lógica (idéntica al legacy):
1. Si no hay `staff_id`, o `sale_total <= 0`, o no hay settings → **no devengar** (devolver `{accrued:false}`).
2. Filtrar reglas aplicables por vigencia (`is_applicable_on(transaction_date)`):
   activa **y** `effective_from <= date <= effective_until` (los null no acotan).
3. Tomar la **primera** regla aplicable (mayor prioridad por el orden).
4. `commission_amount = calculate_commission(sale_total, rule)` (pieza 1). Si `<= 0` → no devengar.
5. Retención fiscal (pieza 3): `(net, tax) = calculate_tax(commission_amount, settings)`.
6. Emitir intención de INSERT en `commissions_transaction` con:
   `staff_id, staff_name, sale_id, sale_reference, appointment_id, sale_amount=sale_total,
    commission_rate=rule.rate, commission_amount, tax_amount=tax, net_commission=net,
    rule_id=rule.id, status='pending', transaction_date`.
7. Devolver `{accrued:true, transaction_id, commission_amount, net_commission}` y emitir
   `commissions.transaction.created`.
- Idempotencia (mejora sobre el legacy, recomendada): si ya existe una transacción no borrada
  con el mismo `sale_id`, no duplicar (devolver `{accrued:false, reason:'already_accrued'}`).

## 3. `calculate_tax`  (helper interno, no es un command)
Origen: `CommissionsSettings.calculate_tax` (models.py).
- Si `apply_tax_withholding` es falso o `tax_withholding_rate <= 0` → `(net=commission, tax=0)`.
- Si no: `tax = quantize(commission * tax_withholding_rate / 100, 0.01)`; `net = commission - tax`.
Usado por `accrue_from_sale` (pieza 2) y por la agregación de payout (pieza 4, ya viene pre-calculado por transacción).

## 4. `create_payout`  (command `commissions.payouts.create`)
Origen: `routes.py::payout_create`. Agregación **batch** sobre N transacciones + generación
atómica de referencia + enlace de las transacciones al lote → no cabe en una sentencia SQL.

Payload: `{staff_id, staff_name, period_start, period_end, notes}`.
Datos que el runtime debe leer y pasar al WASM:
- Transacciones del staff en `[period_start, period_end]` con `status='approved'` y
  `payout_id IS NULL` (query interna; no hace falta exponerla públicamente).
- `commissions.settings.get` → `minimum_payout_amount`.
- Conteo de payouts existentes cuya `reference` empieza por `PAY-{YYYYMM}-` (para la secuencia).

Lógica:
1. Si no hay transacciones aprobadas pendientes de lote en el periodo → error `no_transactions`.
2. `gross = Σ commission_amount`; `tax = Σ tax_amount`; `count = N`; `net = gross - tax`.
3. Si `minimum_payout_amount > 0` y `gross < minimum_payout_amount` → error `below_minimum`
   (incluir `gross` y `minimum` en el mensaje).
4. Generar `reference = "PAY-{YYYYMM}-{seq:04d}"`, `seq = existing_count + 1`. **Atómico**:
   resolver como capacidad de counter del runtime (UPSERT/secuencia) o dentro de la
   transacción del comando, sin ventana SELECT→INSERT que permita colisión.
5. Emitir intención de INSERT en `commissions_payout`:
   `reference, staff_id, staff_name, period_start, period_end, gross_amount=gross,
    tax_amount=tax, adjustments_amount=0, net_amount=net, transaction_count=count,
    notes, status='pending'`.
6. Emitir intención de UPDATE de cada transacción del lote: `payout_id = <nuevo payout id>`
   (todas en la misma transacción).
7. Devolver `{id, reference, gross_amount, tax_amount, net_amount, transaction_count}` y emitir
   `commissions.payout.created`.

> Nota: `adjustments_amount` queda en 0 al crear; si en el futuro se enlazan ajustes
> (`commissions_adjustment.payout_id`) al lote, recalcular `net_amount = gross - tax + Σ adjustments`.

## 5. `process_payout`  (command `commissions.payouts.process`)
Origen: `CommissionsService.process_payout` (services.py). Guarda de estado + **cascada** a
las transacciones del lote → multi-fila, no cabe en una sola UPDATE con el retorno deseado.

Payload: `{payout_id, payment_method, payment_reference}`.
Datos que el runtime debe leer: el payout y sus transacciones (`payout_id = :payout_id`).
Lógica:
1. Guarda: si `payout.status != 'approved'` → error `invalid_status` (debe aprobarse antes).
2. Emitir UPDATE del payout: `status='completed'`, `paid_at=now`, `paid_by_id=current_user`,
   y `payment_method`/`payment_reference` si vienen no vacíos.
3. **Cascada**: por cada transacción del lote no borrada con `status='approved'` →
   UPDATE `status='paid'` (en la misma transacción).
4. Devolver `{id, reference, status, paid_at}` y emitir `commissions.payout.completed`.

## 6. Guarda `has_dependents` de `rule_delete` (validación pre-comando)
Origen: `CommissionsService.delete_rule` (services.py). La sentencia `commands/rule_delete.sql`
solo marca `is_deleted`; la **validación** "no borrar si la regla tiene transacciones
`pending`/`approved`" no está en el SQL.
- Opción A (preferida, sin WASM): el runtime ejecuta un pre-check declarativo (COUNT de
  `commissions_transaction` con `rule_id=:rule_id` y `status IN ('pending','approved')`) y
  rechaza con `has_dependents` antes de aplicar el soft-delete. Documentar como invariant del
  comando.
- Opción B: mover la guarda a un handler WASM `delete_rule` que lea el conteo y devuelva la
  intención de soft-delete o el error. Solo si A no es viable con el motor de invariants.

## 7. `included_in_payslip`  (integración payroll, cross-módulo por evento)
Origen: `CommissionPayout.mark_included_in_payslip` (models.py). Cuando `payroll` confirma una
nómina que incluye comisiones, debe poder marcar el payout como `included_in_payslip` y guardar
`payslip_id` (evita doble conteo). Esto **no** lo hace `commissions` por su cuenta:
- `commissions` debería exponer un command público (futuro) `commissions.payouts.mark_in_payslip`
  `{payout_id, payslip_id}` que `payroll` invoque vía contrato (no import), o escuchar un evento
  `payroll.payslip.confirmed`. Pendiente hasta migrar `payroll`. No bloqueante para este módulo.

---

## Resumen de handlers a implementar en `handler/src/lib.rs`
| función WASM        | command                                      | tipo                |
|---------------------|----------------------------------------------|---------------------|
| `calculate_commission` | `commissions.calculate`                   | preview (lectura)   |
| `accrue_from_sale`     | `commissions.transactions.accrue_from_sale` | evento → insert     |
| `create_payout`        | `commissions.payouts.create`              | batch + insert + cascade |
| `process_payout`       | `commissions.payouts.process`             | guarda + cascade    |

`calculate_tax` (pieza 3) es helper interno compartido por `accrue_from_sale`.
La guarda `has_dependents` (pieza 6) y la integración payslip (pieza 7) se resuelven como
invariant declarativo y contrato cross-módulo respectivamente — ver notas arriba.
