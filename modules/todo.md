# TODO — Handlers Rust→WASM (Tier 2) pendientes de implementar

> Generado tras la migración de los ~100 módulos legacy a hub-next (declarativo + Stencil).
> La migración dejó montado: `module.json` (contrato), UI Stencil con `<data-table>`+Ionic,
> y el **SQL Tier 0 (CRUD)** que ya ejecuta el runtime Rust. **Falta implementar la lógica
> Tier 2** (cálculo/batch/contadores atómicos/fiscal/integraciones) que cada módulo declara
> como handler `{type:wasm}` y documenta en su `WASM-TODO.md`.

## Cómo se implementa un handler (patrón)

Referencia viva (ya implementados en Rust): **inventory, customers, sales, invoice, cash_register**
(`<modulo>/handler/Cargo.toml` + `handler/src/lib.rs` → compila a `<modulo>/dist/handler.wasm`).

Reglas (ARQUITECTURA.md §5.3, §1):
- El WASM corre en sandbox **Extism** y **NUNCA toca la BD**. Recibe el payload + las filas que el
  runtime le pase (leídas por queries declarativas) y **devuelve *intenciones*** (filas a insertar/
  actualizar/borrar, sub-comandos) que **Rust valida y persiste** en una transacción.
- Rust sigue siendo la autoridad: revalida permiso + `hub_id` + payload antes de escribir.
- Nada de SELECT/UPDATE directo a tablas de otro módulo: cross-módulo = queries/commands públicos o eventos.
- Aritmética decimal de precisión fija con redondeo HALF_UP (paridad SQLite↔Postgres).
- El detalle funcional de cada handler está en `<modulo>/WASM-TODO.md` (leerlo antes de implementar).

## Resumen

- Módulos hub-next: **99**
- Handlers Rust→WASM **ya implementados** (POS): **11** en 5 módulos
- Handlers Rust→WASM **pendientes**: **323** repartidos por dominio (checklist abajo)

## Retail / POS  (56 handlers)

### `taxes`  (1)  ·  ver `taxes/WASM-TODO.md`
- [ ] `calculate_tax()` ← command `taxes.calculate`

### `payments`  (1)  ·  ver `payments/WASM-TODO.md`
- [ ] `create_payment()` ← command `payments.payments.create`  · schema `schemas/create_payment.json`

### `pricing`  (3)  ·  ver `pricing/WASM-TODO.md`
- [ ] `create_price_list()` ← command `pricing.price_lists.create`  · schema `schemas/price_list_create.json`
- [ ] `get_price()` ← command `pricing.price_lists.get_price`  · schema `schemas/get_price.json`
- [ ] `calculate_discount()` ← command `pricing.rules.calculate_discount`  · schema `schemas/calculate_discount.json`

### `orders`  (3)  ·  ver `orders/WASM-TODO.md`
- [ ] `create_order()` ← command `orders.create`
- [ ] `complete_order()` ← command `orders.complete`
- [ ] `link_to_sale()` ← command `orders.link_to_sale`

### `tables`  (7)  ·  ver `tables/WASM-TODO.md`
- [ ] `delete_zone()` ← command `tables.zones.delete`
- [ ] `delete_table()` ← command `tables.tables.delete`
- [ ] `bulk_create_tables()` ← command `tables.tables.bulk_create`
- [ ] `open_session()` ← command `tables.sessions.open`
- [ ] `close_session()` ← command `tables.sessions.close`
- [ ] `transfer_session()` ← command `tables.sessions.transfer`
- [ ] `delete_session()` ← command `tables.sessions.delete`

### `kitchen`  — sin handlers WASM (CRUD Tier 0 puro) ✓

### `kitchen_orders`  (6)  ·  ver `kitchen_orders/WASM-TODO.md`
- [ ] `create_order()` ← command `kitchen_orders.orders.create`  · schema `schemas/order_create.json`
- [ ] `update_order_status()` ← command `kitchen_orders.orders.set_status`  · schema `schemas/order_set_status.json`
- [ ] `delete_order()` ← command `kitchen_orders.orders.delete`  · schema `schemas/order_delete.json`
- [ ] `create_order_from_sale()` ← command `kitchen_orders.orders.create_from_sale`
- [ ] `delete_station()` ← command `kitchen_orders.stations.delete`  · schema `schemas/station_delete.json`
- [ ] `set_routing()` ← command `kitchen_orders.stations.set_routing`  · schema `schemas/set_routing.json`

### `services`  (2)  ·  ver `services/WASM-TODO.md`
- [ ] `bulk_create_services()` ← command `services.services.bulk_create`
- [ ] `create_package()` ← command `services.packages.create`

### `quotes`  (4)  ·  ver `quotes/WASM-TODO.md`
- [ ] `create_quote()` ← command `quotes.quotes.create`
- [ ] `update_quote_lines()` ← command `quotes.quotes.update_lines`
- [ ] `convert_to_order()` ← command `quotes.quotes.convert_to_order`
- [ ] `expire_old_quotes()` ← command `quotes.quotes.expire_old`

### `purchase_orders`  (1)  ·  ver `purchase_orders/WASM-TODO.md`
- [ ] `create_order()` ← command `purchase_orders.orders.create`  · schema `schemas/create_order.json`

### `supplier_invoices`  (1)  ·  ver `supplier_invoices/WASM-TODO.md`
- [ ] `create_invoice()` ← command `supplier_invoices.invoices.create`  · schema `schemas/create_invoice.json`

### `credit_notes`  (4)  ·  ver `credit_notes/WASM-TODO.md`
- [ ] `create_credit_note()` ← command `credit_notes.notes.create`
- [ ] `apply_to_invoice()` ← command `credit_notes.notes.apply`
- [ ] `unapply()` ← command `credit_notes.notes.unapply`
- [ ] `cancel_credit_note()` ← command `credit_notes.notes.cancel`

### `invoice_series`  (2)  ·  ver `invoice_series/WASM-TODO.md`
- [ ] `set_as_default()` ← command `invoice_series.series.set_default`  · schema `schemas/series_get.json`
- [ ] `get_next_number()` ← command `invoice_series.series.next_number`  · schema `schemas/series_next_number.json`

### `payment_gateways`  (5)  ·  ver `payment_gateways/WASM-TODO.md`
- [ ] `initiate_payment()` ← command `payment_gateways.transactions.initiate`
- [ ] `mark_succeeded()` ← command `payment_gateways.transactions.mark_succeeded`
- [ ] `mark_failed()` ← command `payment_gateways.transactions.mark_failed`
- [ ] `refund_transaction()` ← command `payment_gateways.transactions.refund`
- [ ] `transactions_summary()` ← command `payment_gateways.transactions.summary`

### `stripe`  (4)  ·  ver `stripe/WASM-TODO.md`
- [ ] `record_charge()` ← command `stripe.charges.record`
- [ ] `record_refund()` ← command `stripe.refunds.record`
- [ ] `record_webhook_event()` ← command `stripe.webhooks.record`
- [ ] `get_charges_summary()` ← command `stripe.charges.summary`

### `cart_checkout`  (6)  ·  ver `cart_checkout/WASM-TODO.md`
- [ ] `add_to_cart()` ← command `cart_checkout.items.add`
- [ ] `update_cart_item()` ← command `cart_checkout.items.update`
- [ ] `clear_cart()` ← command `cart_checkout.carts.clear`
- [ ] `cleanup_expired_carts()` ← command `cart_checkout.carts.cleanup_expired`
- [ ] `initiate_checkout()` ← command `cart_checkout.checkout.initiate`
- [ ] `complete_checkout()` ← command `cart_checkout.orders.complete`

### `online_store`  — sin handlers WASM (CRUD Tier 0 puro) ✓

### `reservations`  — sin handlers WASM (CRUD Tier 0 puro) ✓

### `online_booking`  — sin handlers WASM (CRUD Tier 0 puro) ✓

### `appointments`  (4)  ·  ver `appointments/WASM-TODO.md`
- [ ] `create_appointment()` ← command `appointments.appointments.create`  · schema `schemas/appointment_create.json`
- [ ] `bulk_create()` ← command `appointments.appointments.bulk_create`  · schema `schemas/appointment_create.json`
- [ ] `bulk_delete()` ← command `appointments.appointments.bulk_delete`
- [ ] `materialize_recurring()` ← command `appointments.recurring.materialize`

### `schedules`  (2)  ·  ver `schedules/WASM-TODO.md`
- [ ] `bulk_create_special_days()` ← command `schedules.bulk_create_special_days`
- [ ] `is_open()` ← command `schedules.is_open`

### `notes`  — sin handlers WASM (CRUD Tier 0 puro) ✓

## Finanzas / Fiscal  (90 handlers)

### `accounting`  (4)  ·  ver `accounting/WASM-TODO.md`
- [ ] `create_account()` ← command `accounting.accounts.create`  · schema `schemas/account_create.json`
- [ ] `create_entry()` ← command `accounting.entries.create`  · schema `schemas/entry_create.json`
- [ ] `post_entry()` ← command `accounting.entries.post`  · schema `schemas/entry_post.json`
- [ ] `cancel_entry()` ← command `accounting.entries.cancel`  · schema `schemas/entry_cancel.json`

### `general_ledger`  (3)  ·  ver `general_ledger/WASM-TODO.md`
- [ ] `create_entry()` ← command `general_ledger.entries.create`  · schema `schemas/entry_create.json`
- [ ] `post_entry()` ← command `general_ledger.entries.post`  · schema `schemas/entry_post.json`
- [ ] `reverse_entry()` ← command `general_ledger.entries.reverse`  · schema `schemas/entry_reverse.json`

### `financial_statements`  (5)  ·  ver `financial_statements/WASM-TODO.md`
- [ ] `generate_balance_sheet()` ← command `financial_statements.reports.generate_balance_sheet`  · schema `schemas/generate_balance_sheet.json`
- [ ] `generate_profit_loss()` ← command `financial_statements.reports.generate_profit_loss`  · schema `schemas/generate_profit_loss.json`
- [ ] `generate_cash_flow()` ← command `financial_statements.reports.generate_cash_flow`  · schema `schemas/generate_cash_flow.json`
- [ ] `export_report()` ← command `financial_statements.reports.export`  · schema `schemas/export_report.json`
- [ ] `compare_reports()` ← command `financial_statements.reports.compare`  · schema `schemas/compare_reports.json`

### `bank_reconciliation`  (4)  ·  ver `bank_reconciliation/WASM-TODO.md`
- [ ] `create_statement()` ← command `bank_reconciliation.statements.create`  · schema `schemas/statement_create.json`
- [ ] `remove_match()` ← command `bank_reconciliation.matches.remove`  · schema `schemas/match_remove.json`
- [ ] `auto_match_by_amount_and_date()` ← command `bank_reconciliation.matches.auto_match`  · schema `schemas/auto_match.json`
- [ ] `close_statement()` ← command `bank_reconciliation.statements.close`  · schema `schemas/statement_close.json`

### `banking`  (1)  ·  ver `banking/WASM-TODO.md`
- [ ] `add_transaction()` ← command `banking.transactions.add`  · schema `schemas/transaction_add.json`

### `expenses`  (3)  ·  ver `expenses/WASM-TODO.md`
- [ ] `submit_expense()` ← command `expenses.expenses.submit`  · schema `schemas/expense_submit.json`
- [ ] `approve_expense()` ← command `expenses.expenses.approve`  · schema `schemas/expense_approve.json`
- [ ] `reject_expense()` ← command `expenses.expenses.reject`  · schema `schemas/expense_reject.json`

### `fixed_assets`  (3)  ·  ver `fixed_assets/WASM-TODO.md`
- [ ] `dispose_asset()` ← command `fixed_assets.assets.dispose`  · schema `schemas/asset_dispose.json`
- [ ] `post_depreciation()` ← command `fixed_assets.depreciations.post`  · schema `schemas/depreciation_post.json`
- [ ] `run_monthly_depreciation()` ← command `fixed_assets.depreciations.run_monthly`  · schema `schemas/depreciation_run_monthly.json`

### `cashflow_forecasting`  (3)  ·  ver `cashflow_forecasting/WASM-TODO.md`
- [ ] `run_projection()` ← command `cashflow_forecasting.projections.run`  · schema `schemas/run_projection.json`
- [ ] `compare_scenarios()` ← command `cashflow_forecasting.scenarios.compare`  · schema `schemas/compare_scenarios.json`
- [ ] `get_break_even_point()` ← command `cashflow_forecasting.scenarios.break_even`  · schema `schemas/break_even.json`

### `collections`  (5)  ·  ver `collections/WASM-TODO.md`
- [ ] `create_collection()` ← command `collections.collections.create`  · schema `schemas/create_collection.json`
- [ ] `allocate_to_invoice()` ← command `collections.collections.allocate`  · schema `schemas/allocate_to_invoice.json`
- [ ] `unallocate()` ← command `collections.collections.unallocate`  · schema `schemas/unallocate.json`
- [ ] `refund_collection()` ← command `collections.collections.refund`  · schema `schemas/refund_collection.json`
- [ ] `cancel_collection()` ← command `collections.collections.cancel`  · schema `schemas/cancel_collection.json`

### `credit_risk`  (4)  ·  ver `credit_risk/WASM-TODO.md`
- [ ] `update_limit()` ← command `credit_risk.customers.update_limit`  · schema `schemas/customer_update_limit.json`
- [ ] `record_event()` ← command `credit_risk.events.record`  · schema `schemas/event_record.json`
- [ ] `update_score()` ← command `credit_risk.customers.update_score`  · schema `schemas/customer_update_score.json`
- [ ] `check_limit()` ← command `credit_risk.customers.check_limit`  · schema `schemas/customer_check_limit.json`

### `commissions`  (4)  ·  ver `commissions/WASM-TODO.md`
- [ ] `create_payout()` ← command `commissions.payouts.create`  · schema `schemas/payout_create.json`
- [ ] `process_payout()` ← command `commissions.payouts.process`  · schema `schemas/payout_process.json`
- [ ] `calculate_commission()` ← command `commissions.calculate`  · schema `schemas/calculate.json`
- [ ] `accrue_from_sale()` ← command `commissions.transactions.accrue_from_sale`  · schema `schemas/accrue_from_sale.json`

### `sepa_remittances`  (5)  ·  ver `sepa_remittances/WASM-TODO.md`
- [ ] `create_direct_debit()` ← command `sepa_remittances.remittances.create_direct_debit`  · schema `schemas/create_direct_debit.json`
- [ ] `create_credit_transfer()` ← command `sepa_remittances.remittances.create_credit_transfer`  · schema `schemas/create_credit_transfer.json`
- [ ] `generate_xml()` ← command `sepa_remittances.remittances.generate_xml`  · schema `schemas/generate_xml.json`
- [ ] `mark_processed()` ← command `sepa_remittances.remittances.mark_processed`  · schema `schemas/mark_processed.json`
- [ ] `mark_rejected()` ← command `sepa_remittances.remittances.mark_rejected`  · schema `schemas/mark_rejected.json`

### `subscriptions`  (5)  ·  ver `subscriptions/WASM-TODO.md`
- [ ] `create_subscription()` ← command `subscriptions.subscriptions.create`  · schema `schemas/subscription_create.json`
- [ ] `activate_subscription()` ← command `subscriptions.subscriptions.activate`  · schema `schemas/subscription_activate.json`
- [ ] `cancel_subscription()` ← command `subscriptions.subscriptions.cancel`  · schema `schemas/subscription_cancel.json`
- [ ] `generate_billing_cycle()` ← command `subscriptions.cycles.generate`  · schema `schemas/cycle_generate.json`
- [ ] `process_renewals()` ← command `subscriptions.subscriptions.process_renewals`

### `verifactu`  (4)  ·  ver `verifactu/WASM-TODO.md`
- [ ] `create_record()` ← command `verifactu.records.create`  · schema `schemas/record_create.json`
- [ ] `transmit_record()` ← command `verifactu.records.transmit`  · schema `schemas/record_transmit.json`
- [ ] `process_contingency_queue()` ← command `verifactu.contingency.process`  · schema `schemas/contingency_process.json`
- [ ] `validate_chain()` ← command `verifactu.chain.validate`  · schema `schemas/chain_validate.json`

### `fiscal_france`  (7)  ·  ver `fiscal_france/WASM-TODO.md`
- [ ] `update_config()` ← command `fiscal_france.config.update`  · schema `schemas/config_update.json`
- [ ] `create_facturx()` ← command `fiscal_france.facturx.create`  · schema `schemas/facturx_create.json`
- [ ] `generate_facturx_xml()` ← command `fiscal_france.facturx.generate_xml`  · schema `schemas/facturx_generate_xml.json`
- [ ] `submit_facturx()` ← command `fiscal_france.facturx.submit`  · schema `schemas/facturx_submit.json`
- [ ] `create_chorus_invoice()` ← command `fiscal_france.chorus.create`  · schema `schemas/chorus_create.json`
- [ ] `update_chorus_status()` ← command `fiscal_france.chorus.update_status`  · schema `schemas/chorus_update_status.json`
- [ ] `generate_fec()` ← command `fiscal_france.fec.generate`  · schema `schemas/fec_generate.json`

### `fiscal_germany`  (8)  ·  ver `fiscal_germany/WASM-TODO.md`
- [ ] `upsert_config()` ← command `fiscal_germany.config.upsert`  · schema `schemas/config_upsert.json`
- [ ] `create_xrechnung()` ← command `fiscal_germany.xrechnung.create`  · schema `schemas/xrechnung_create.json`
- [ ] `generate_xrechnung_xml()` ← command `fiscal_germany.xrechnung.generate_xml`  · schema `schemas/xrechnung_id.json`
- [ ] `validate_xrechnung()` ← command `fiscal_germany.xrechnung.validate`  · schema `schemas/xrechnung_id.json`
- [ ] `submit_xrechnung()` ← command `fiscal_germany.xrechnung.submit`  · schema `schemas/xrechnung_id.json`
- [ ] `create_zugferd()` ← command `fiscal_germany.zugferd.create`  · schema `schemas/zugferd_create.json`
- [ ] `generate_zugferd_pdf()` ← command `fiscal_germany.zugferd.generate_pdf`  · schema `schemas/zugferd_id.json`
- [ ] `generate_gobd_export()` ← command `fiscal_germany.gobd.generate`  · schema `schemas/gobd_generate.json`

### `fiscal_italy`  (7)  ·  ver `fiscal_italy/WASM-TODO.md`
- [ ] `config_upsert()` ← command `fiscal_italy.config.upsert`  · schema `schemas/config_upsert.json`
- [ ] `fatturapa_create()` ← command `fiscal_italy.fatturapa.create`  · schema `schemas/fatturapa_create.json`
- [ ] `fatturapa_generate_xml()` ← command `fiscal_italy.fatturapa.generate_xml`  · schema `schemas/fatturapa_generate_xml.json`
- [ ] `fatturapa_submit_to_sdi()` ← command `fiscal_italy.fatturapa.submit_to_sdi`  · schema `schemas/fatturapa_submit.json`
- [ ] `fatturapa_update_sdi_status()` ← command `fiscal_italy.fatturapa.update_sdi_status`  · schema `schemas/fatturapa_update_sdi_status.json`
- [ ] `esterometro_declaration_generate()` ← command `fiscal_italy.esterometro.declaration.generate`  · schema `schemas/esterometro_declaration_generate.json`
- [ ] `esterometro_declaration_submit()` ← command `fiscal_italy.esterometro.declaration.submit`  · schema `schemas/esterometro_declaration_submit.json`

### `fiscal_portugal`  (7)  ·  ver `fiscal_portugal/WASM-TODO.md`
- [ ] `update_config()` ← command `fiscal_portugal.config.update`  · schema `schemas/config_update.json`
- [ ] `generate_saft()` ← command `fiscal_portugal.saft.generate`  · schema `schemas/saft_generate.json`
- [ ] `submit_saft()` ← command `fiscal_portugal.saft.submit`  · schema `schemas/saft_submit.json`
- [ ] `assign_atcud()` ← command `fiscal_portugal.atcud.assign`  · schema `schemas/atcud_assign.json`
- [ ] `create_at_communication()` ← command `fiscal_portugal.at_comm.create`  · schema `schemas/at_comm_create.json`
- [ ] `submit_at_communication()` ← command `fiscal_portugal.at_comm.submit`  · schema `schemas/at_comm_submit.json`
- [ ] `update_communication_status()` ← command `fiscal_portugal.at_comm.set_status`  · schema `schemas/at_comm_set_status.json`

### `fiscal_romania`  (8)  ·  ver `fiscal_romania/WASM-TODO.md`
- [ ] `update_config()` ← command `fiscal_romania.config.update`  · schema `schemas/config_update.json`
- [ ] `create_efactura()` ← command `fiscal_romania.efactura.create`  · schema `schemas/efactura_create.json`
- [ ] `generate_efactura_xml()` ← command `fiscal_romania.efactura.generate_xml`  · schema `schemas/efactura_generate_xml.json`
- [ ] `submit_efactura()` ← command `fiscal_romania.efactura.submit`  · schema `schemas/efactura_submit.json`
- [ ] `validate_efactura()` ← command `fiscal_romania.efactura.validate`  · schema `schemas/efactura_validate.json`
- [ ] `create_etransport()` ← command `fiscal_romania.etransport.create`  · schema `schemas/etransport_create.json`
- [ ] `submit_etransport()` ← command `fiscal_romania.etransport.submit`  · schema `schemas/etransport_submit.json`
- [ ] `generate_jpk()` ← command `fiscal_romania.jpk.generate`  · schema `schemas/jpk_generate.json`

## Inventario / Producción / Logística  (57 handlers)

### `multi_warehouse`  (5)  ·  ver `multi_warehouse/WASM-TODO.md`
- [ ] `create_warehouse()` ← command `multi_warehouse.warehouses.create`  · schema `schemas/warehouse_create.json`
- [ ] `set_default_warehouse()` ← command `multi_warehouse.warehouses.set_default`  · schema `schemas/warehouse_set_default.json`
- [ ] `create_transfer()` ← command `multi_warehouse.transfers.create`  · schema `schemas/transfer_create.json`
- [ ] `dispatch_transfer()` ← command `multi_warehouse.transfers.dispatch`  · schema `schemas/transfer_dispatch.json`
- [ ] `receive_transfer()` ← command `multi_warehouse.transfers.receive`  · schema `schemas/transfer_receive.json`

### `lots_serials`  (3)  ·  ver `lots_serials/WASM-TODO.md`
- [ ] `create_lot()` ← command `lots_serials.lots.create`  · schema `schemas/lot_create.json`
- [ ] `record_movement()` ← command `lots_serials.lots.record_movement`  · schema `schemas/movement_record.json`
- [ ] `mark_recalled()` ← command `lots_serials.lots.mark_recalled`  · schema `schemas/lot_mark_recalled.json`

### `traceability`  (3)  ·  ver `traceability/WASM-TODO.md`
- [ ] `record_event()` ← command `traceability.events.record`  · schema `schemas/record_event.json`
- [ ] `recall_impact()` ← command `traceability.recall.impact`  · schema `schemas/recall_impact.json`
- [ ] `search_by_metadata()` ← command `traceability.events.search_metadata`  · schema `schemas/search_metadata.json`

### `stock_sync`  (4)  ·  ver `stock_sync/WASM-TODO.md`
- [ ] `start_sync()` ← command `stock_sync.runs.start`  · schema `schemas/sync_start.json`
- [ ] `complete_sync()` ← command `stock_sync.runs.complete`  · schema `schemas/sync_complete.json`
- [ ] `detect_conflict()` ← command `stock_sync.conflicts.detect`  · schema `schemas/conflict_detect.json`
- [ ] `resolve_conflict()` ← command `stock_sync.conflicts.resolve`  · schema `schemas/conflict_resolve.json`

### `bom`  (3)  ·  ver `bom/WASM-TODO.md`
- [ ] `set_as_default()` ← command `bom.boms.set_default`  · schema `schemas/bom_set_default.json`
- [ ] `explode_bom()` ← command `bom.boms.explode`  · schema `schemas/bom_explode.json`
- [ ] `clone_bom()` ← command `bom.boms.clone`  · schema `schemas/bom_clone.json`

### `mrp`  (1)  ·  ver `mrp/WASM-TODO.md`
- [ ] `create_run()` ← command `mrp.runs.create`  · schema `schemas/run_create.json`

### `manufacturing_orders`  (3)  ·  ver `manufacturing_orders/WASM-TODO.md`
- [ ] `create_mo()` ← command `manufacturing_orders.orders.create`  · schema `schemas/create_mo.json`
- [ ] `record_consumption()` ← command `manufacturing_orders.materials.record_consumption`  · schema `schemas/record_consumption.json`
- [ ] `get_mo_summary()` ← command `manufacturing_orders.orders.summary`  · schema `schemas/get_mo_summary.json`

### `work_centers`  (4)  ·  ver `work_centers/WASM-TODO.md`
- [ ] `log_event()` ← command `work_centers.events.log`  · schema `schemas/event_log.json`
- [ ] `end_event()` ← command `work_centers.events.end`  · schema `schemas/event_end.json`
- [ ] `get_utilization()` ← command `work_centers.kpi.utilization`  · schema `schemas/kpi_utilization.json`
- [ ] `get_oee()` ← command `work_centers.kpi.oee`  · schema `schemas/kpi_oee.json`

### `picking_packing`  (7)  ·  ver `picking_packing/WASM-TODO.md`
- [ ] `create_pick()` ← command `picking_packing.picks.create`  · schema `schemas/pick_create.json`
- [ ] `record_pick_line()` ← command `picking_packing.picks.record_line`  · schema `schemas/pick_record_line.json`
- [ ] `complete_pick()` ← command `picking_packing.picks.complete`  · schema `schemas/pick_complete.json`
- [ ] `cancel_pick()` ← command `picking_packing.picks.cancel`  · schema `schemas/pick_cancel.json`
- [ ] `create_package()` ← command `picking_packing.packages.create`  · schema `schemas/package_create.json`
- [ ] `seal_package()` ← command `picking_packing.packages.seal`  · schema `schemas/package_seal.json`
- [ ] `ship_package()` ← command `picking_packing.packages.ship`  · schema `schemas/package_ship.json`

### `delivery`  (4)  ·  ver `delivery/WASM-TODO.md`
- [ ] `delete_zone()` ← command `delivery.zones.delete`  · schema `schemas/zone_delete.json`
- [ ] `delete_driver()` ← command `delivery.drivers.delete`  · schema `schemas/driver_delete.json`
- [ ] `create_order()` ← command `delivery.orders.create`  · schema `schemas/order_create.json`
- [ ] `update_order()` ← command `delivery.orders.update`  · schema `schemas/order_update.json`

### `carriers`  (1)  ·  ver `carriers/WASM-TODO.md`
- [ ] `create_shipment()` ← command `carriers.shipments.create`  · schema `schemas/shipment_create.json`

### `courier_integrations`  (6)  ·  ver `courier_integrations/WASM-TODO.md`
- [ ] `record_call()` ← command `courier_integrations.calls.record`  · schema `schemas/record_call.json`
- [ ] `create_shipment_via_courier()` ← command `courier_integrations.shipments.create`  · schema `schemas/create_shipment.json`
- [ ] `get_label_url()` ← command `courier_integrations.shipments.get_label`  · schema `schemas/get_label.json`
- [ ] `track_shipment_via_courier()` ← command `courier_integrations.shipments.track`  · schema `schemas/track_shipment.json`
- [ ] `cancel_shipment_via_courier()` ← command `courier_integrations.shipments.cancel`  · schema `schemas/cancel_shipment.json`
- [ ] `get_api_metrics()` ← command `courier_integrations.metrics.get`  · schema `schemas/get_api_metrics.json`

### `marketplaces`  (2)  ·  ver `marketplaces/WASM-TODO.md`
- [ ] `import_order()` ← command `marketplaces.orders.import`  · schema `schemas/order_import.json`
- [ ] `complete_sync()` ← command `marketplaces.syncs.complete`  · schema `schemas/sync_complete.json`

### `glovo`  (3)  ·  ver `glovo/WASM-TODO.md`
- [ ] `import_order()` ← command `glovo.orders.import`  · schema `schemas/import_order.json`
- [ ] `complete_menu_sync()` ← command `glovo.menu_syncs.complete`  · schema `schemas/complete_menu_sync.json`
- [ ] `sync_product()` ← command `glovo.products.sync`  · schema `schemas/sync_product.json`

### `uber_eats`  (6)  ·  ver `uber_eats/WASM-TODO.md`
- [ ] `import_order()` ← command `uber_eats.orders.import`  · schema `schemas/order_import.json`
- [ ] `update_order_status()` ← command `uber_eats.orders.update_status`  · schema `schemas/order_update_status.json`
- [ ] `cancel_order()` ← command `uber_eats.orders.cancel`  · schema `schemas/order_cancel.json`
- [ ] `sync_menu()` ← command `uber_eats.menus.sync`  · schema `schemas/menu_sync.json`
- [ ] `record_event()` ← command `uber_eats.events.record`  · schema `schemas/event_record.json`
- [ ] `store_summary()` ← command `uber_eats.stores.summary`  · schema `schemas/store_summary.json`

### `locations`  (2)  ·  ver `locations/WASM-TODO.md`
- [ ] `update_stock_position()` ← command `locations.stock.update_position`  · schema `schemas/stock_update.json`
- [ ] `count_bin()` ← command `locations.stock.count_bin`  · schema `schemas/count_bin.json`

## CRM / Ventas / Comunicaciones  (46 handlers)

### `leads`  (6)  ·  ver `leads/WASM-TODO.md`
- [ ] `create_lead()` ← command `leads.leads.create`  · schema `schemas/lead_create.json`
- [ ] `mark_contacted()` ← command `leads.leads.mark_contacted`  · schema `schemas/lead_id.json`
- [ ] `qualify_lead()` ← command `leads.leads.qualify`  · schema `schemas/lead_qualify.json`
- [ ] `unqualify_lead()` ← command `leads.leads.unqualify`  · schema `schemas/lead_reason.json`
- [ ] `convert_lead()` ← command `leads.leads.convert`
- [ ] `mark_lost()` ← command `leads.leads.mark_lost`  · schema `schemas/lead_reason.json`

### `opportunities`  (3)  ·  ver `opportunities/WASM-TODO.md`
- [ ] `create_opportunity()` ← command `opportunities.opportunities.create`  · schema `schemas/opportunity_create.json`
- [ ] `mark_won()` ← command `opportunities.opportunities.mark_won`  · schema `schemas/mark_won.json`
- [ ] `log_activity()` ← command `opportunities.activities.log`  · schema `schemas/log_activity.json`

### `pipeline`  (4)  ·  ver `pipeline/WASM-TODO.md`
- [ ] `create_pipeline()` ← command `pipeline.pipelines.create`  · schema `schemas/pipeline_create.json`
- [ ] `create_deal()` ← command `pipeline.deals.create`  · schema `schemas/deal_create.json`
- [ ] `move_deal()` ← command `pipeline.deals.move`  · schema `schemas/deal_move.json`
- [ ] `pipeline_metrics()` ← command `pipeline.pipelines.metrics`  · schema `schemas/pipeline_metrics.json`

### `contracts`  (2)  ·  ver `contracts/WASM-TODO.md`
- [ ] `create_contract()` ← command `contracts.contracts.create`
- [ ] `expire_old_contracts()` ← command `contracts.contracts.expire_old`

### `communications`  (6)  ·  ver `communications/WASM-TODO.md`
- [ ] `compose_send()` ← command `communications.compose.send`
- [ ] `reply_to_thread()` ← command `communications.threads.reply`
- [ ] `schedule_email()` ← command `communications.compose.schedule`
- [ ] `assign_thread()` ← command `communications.threads.assign`
- [ ] `sync_account()` ← command `communications.email.sync`
- [ ] `upsert_settings()` ← command `communications.settings.upsert`

### `email_marketing`  (5)  ·  ver `email_marketing/WASM-TODO.md`
- [ ] `subscribe()` ← command `email_marketing.subscribers.subscribe`  · schema `schemas/subscribe.json`
- [ ] `unsubscribe()` ← command `email_marketing.subscribers.unsubscribe`  · schema `schemas/unsubscribe.json`
- [ ] `schedule_campaign()` ← command `email_marketing.campaigns.schedule`  · schema `schemas/campaign_schedule.json`
- [ ] `send_campaign()` ← command `email_marketing.campaigns.send`  · schema `schemas/campaign_send.json`
- [ ] `record_event()` ← command `email_marketing.events.record`  · schema `schemas/event_record.json`

### `whatsapp_inbox`  (1)  ·  ver `whatsapp_inbox/WASM-TODO.md`
- [ ] `fulfill_request()` ← command `whatsapp_inbox.requests.fulfill`  · schema `schemas/request_fulfill.json`

### `messaging`  (2)  ·  ver `messaging/WASM-TODO.md`
- [ ] `send_message()` ← command `messaging.messages.send`  · schema `schemas/message_send.json`
- [ ] `send_campaign()` ← command `messaging.campaigns.send`  · schema `schemas/campaign_send.json`

### `tickets`  (8)  ·  ver `tickets/WASM-TODO.md`
- [ ] `create_ticket()` ← command `tickets.tickets.create`  · schema `schemas/ticket_create.json`
- [ ] `assign_ticket()` ← command `tickets.tickets.assign`  · schema `schemas/ticket_assign.json`
- [ ] `update_status()` ← command `tickets.tickets.update_status`  · schema `schemas/ticket_update_status.json`
- [ ] `add_comment()` ← command `tickets.comments.add`  · schema `schemas/comment_add.json`
- [ ] `resolve_ticket()` ← command `tickets.tickets.resolve`  · schema `schemas/ticket_resolve.json`
- [ ] `close_ticket()` ← command `tickets.tickets.close`  · schema `schemas/ticket_close.json`
- [ ] `reopen_ticket()` ← command `tickets.tickets.reopen`  · schema `schemas/ticket_reopen.json`
- [ ] `check_sla_breach()` ← command `tickets.slas.check_breach`  · schema `schemas/sla_check_breach.json`

### `customer_portal`  (4)  ·  ver `customer_portal/WASM-TODO.md`
- [ ] `create_invitation()` ← command `customer_portal.invitations.create`  · schema `schemas/invitation_create.json`
- [ ] `accept_invitation()` ← command `customer_portal.invitations.accept`  · schema `schemas/invitation_accept.json`
- [ ] `create_session()` ← command `customer_portal.sessions.create`  · schema `schemas/session_create.json`
- [ ] `cleanup_expired_sessions()` ← command `customer_portal.sessions.cleanup_expired`

### `project_billing`  (3)  ·  ver `project_billing/WASM-TODO.md`
- [ ] `create_contract()` ← command `project_billing.contracts.create`  · schema `schemas/contract_create.json`
- [ ] `generate_invoice()` ← command `project_billing.invoices.generate`  · schema `schemas/invoice_generate.json`
- [ ] `mark_invoice_paid()` ← command `project_billing.invoices.mark_paid`  · schema `schemas/invoice_mark_paid.json`

### `project_costing`  (2)  ·  ver `project_costing/WASM-TODO.md`
- [ ] `get_project_total_cost()` ← command `project_costing.reports.project_total`
- [ ] `get_budget_vs_actual()` ← command `project_costing.reports.budget_vs_actual`

## RRHH / Operaciones / Plataforma  (47 handlers)

### `attendance`  (4)  ·  ver `attendance/WASM-TODO.md`
- [ ] `clock_in()` ← command `attendance.records.clock_in`
- [ ] `clock_out()` ← command `attendance.records.clock_out`
- [ ] `update_record()` ← command `attendance.records.update`
- [ ] `delete_record()` ← command `attendance.records.delete`

### `leave`  (4)  ·  ver `leave/WASM-TODO.md`
- [ ] `delete_leave_type()` ← command `leave.types.delete`  · schema `schemas/type_delete.json`
- [ ] `create_request()` ← command `leave.requests.create`  · schema `schemas/request_create.json`
- [ ] `approve_request()` ← command `leave.requests.approve`  · schema `schemas/request_approve.json`
- [ ] `set_balance()` ← command `leave.balances.set`  · schema `schemas/balance_set.json`

### `payroll`  (3)  ·  ver `payroll/WASM-TODO.md`
- [ ] `delete_payslip()` ← command `payroll.payslips.delete`  · schema `schemas/payslip_delete.json`
- [ ] `approve_payslip()` ← command `payroll.payslips.approve`  · schema `schemas/payslip_approve.json`
- [ ] `calculate_payslip()` ← command `payroll.calculate`  · schema `schemas/calculate.json`

### `staff`  (4)  ·  ver `staff/WASM-TODO.md`
- [ ] `deactivate_staff_member()` ← command `staff.members.deactivate`  · schema `schemas/member_deactivate.json`
- [ ] `bulk_create_staff_members()` ← command `staff.members.bulk_create`  · schema `schemas/member_bulk_create.json`
- [ ] `create_time_off()` ← command `staff.time_off.create`  · schema `schemas/time_off_create.json`
- [ ] `create_schedule()` ← command `staff.schedules.create`  · schema `schemas/schedule_create.json`

### `timesheets`  (3)  ·  ver `timesheets/WASM-TODO.md`
- [ ] `create_entry()` ← command `timesheets.entries.create`  · schema `schemas/entry_create.json`
- [ ] `update_entry()` ← command `timesheets.entries.update`  · schema `schemas/entry_update.json`
- [ ] `approve_timesheet()` ← command `timesheets.approvals.approve`  · schema `schemas/approval_approve.json`

### `time_control`  (3)  ·  ver `time_control/WASM-TODO.md`
- [ ] `update_settings()` ← command `time_control.settings.update`  · schema `schemas/settings_update.json`
- [ ] `clock_action()` ← command `time_control.records.clock`  · schema `schemas/record_clock.json`
- [ ] `recalculate_daily_summary()` ← command `time_control.summaries.recalculate`  · schema `schemas/summary_recalculate.json`

### `workforce_planning`  (1)  ·  ver `workforce_planning/WASM-TODO.md`
- [ ] `create_shift_assignment()` ← command `workforce_planning.assignments.create`  · schema `schemas/assignment_create.json`

### `tasks`  (3)  ·  ver `tasks/WASM-TODO.md`
- [ ] `create_task()` ← command `tasks.tasks.create`  · schema `schemas/create_task.json`
- [ ] `update_status()` ← command `tasks.tasks.update_status`  · schema `schemas/update_status.json`
- [ ] `complete_task()` ← command `tasks.tasks.complete`  · schema `schemas/complete_task.json`

### `gantt`  (5)  ·  ver `gantt/WASM-TODO.md`
- [ ] `add_task()` ← command `gantt.tasks.add`  · schema `schemas/task_add.json`
- [ ] `add_dependency()` ← command `gantt.dependencies.add`  · schema `schemas/dependency_add.json`
- [ ] `update_task_progress()` ← command `gantt.tasks.update_progress`  · schema `schemas/task_update_progress.json`
- [ ] `shift_task()` ← command `gantt.tasks.shift`  · schema `schemas/task_shift.json`
- [ ] `calculate_critical_path()` ← command `gantt.projects.critical_path`  · schema `schemas/project_critical_path.json`

### `workflows`  (2)  ·  ver `workflows/WASM-TODO.md`
- [ ] `execute_workflow()` ← command `workflows.workflows.execute`  · schema `schemas/workflow_execute.json`
- [ ] `evaluate_conditions()` ← command `workflows.conditions.evaluate`  · schema `schemas/conditions_evaluate.json`

### `rules_triggers`  (4)  ·  ver `rules_triggers/WASM-TODO.md`
- [ ] `create_rule()` ← command `rules_triggers.rules.create`  · schema `schemas/rule_create.json`
- [ ] `update_rule()` ← command `rules_triggers.rules.update`  · schema `schemas/rule_update.json`
- [ ] `evaluate_rules()` ← command `rules_triggers.rules.evaluate`  · schema `schemas/rule_evaluate.json`
- [ ] `test_rule()` ← command `rules_triggers.rules.test`  · schema `schemas/rule_test.json`

### `activities`  (3)  ·  ver `activities/WASM-TODO.md`
- [ ] `mark_completed()` ← command `activities.activities.complete`  · schema `schemas/activity_complete.json`
- [ ] `cancel_activity()` ← command `activities.activities.cancel`  · schema `schemas/activity_cancel.json`
- [ ] `get_activity_stats()` ← command `activities.activities.stats`  · schema `schemas/activity_stats.json`

### `audit_log`  (2)  ·  ver `audit_log/WASM-TODO.md`
- [ ] `generate_report()` ← command `audit_log.reports.generate`  · schema `schemas/report_generate.json`
- [ ] `cleanup_old_events()` ← command `audit_log.events.cleanup`  · schema `schemas/events_cleanup.json`

### `setup`  (1)  ·  ver `setup/WASM-TODO.md`
- [ ] `apply_template()` ← command `setup.template.apply`  · schema `schemas/template_apply.json`

### `training`  (5)  ·  ver `training/WASM-TODO.md`
- [ ] `delete_program()` ← command `training.programs.delete`  · schema `schemas/program_delete.json`
- [ ] `delete_skill()` ← command `training.skills.delete`  · schema `schemas/skill_delete.json`
- [ ] `enroll_employee()` ← command `training.enrollments.enroll`  · schema `schemas/enrollment_enroll.json`
- [ ] `update_training_status()` ← command `training.enrollments.update_status`  · schema `schemas/enrollment_update_status.json`
- [ ] `save_settings()` ← command `training.settings.save`  · schema `schemas/settings_save.json`

## AI / Analítica  (27 handlers)

### `ai_agents`  (4)  ·  ver `ai_agents/WASM-TODO.md`
- [ ] `start_run()` ← command `ai_agents.runs.start`  · schema `schemas/run_start.json`
- [ ] `record_step()` ← command `ai_agents.runs.record_step`  · schema `schemas/run_record_step.json`
- [ ] `complete_run()` ← command `ai_agents.runs.complete`  · schema `schemas/run_complete.json`
- [ ] `fail_run()` ← command `ai_agents.runs.fail`  · schema `schemas/run_fail.json`

### `ai_predictions`  (4)  ·  ver `ai_predictions/WASM-TODO.md`
- [ ] `update_model_accuracy()` ← command `ai_predictions.models.update_accuracy`  · schema `schemas/model_update_accuracy.json`
- [ ] `record_prediction()` ← command `ai_predictions.predictions.record`  · schema `schemas/prediction_record.json`
- [ ] `record_feedback()` ← command `ai_predictions.feedback.record`  · schema `schemas/feedback_record.json`
- [ ] `get_model_accuracy()` ← command `ai_predictions.models.accuracy`  · schema `schemas/model_accuracy.json`

### `ai_reports`  (3)  ·  ver `ai_reports/WASM-TODO.md`
- [ ] `create_request()` ← command `ai_reports.requests.create`  · schema `schemas/request_create.json`
- [ ] `run_request()` ← command `ai_reports.requests.run`  · schema `schemas/request_run.json`
- [ ] `cancel_request()` ← command `ai_reports.requests.cancel`  · schema `schemas/request_cancel.json`

### `ai_setup_wizard`  (5)  ·  ver `ai_setup_wizard/WASM-TODO.md`
- [ ] `start_session()` ← command `ai_setup_wizard.sessions.start`  · schema `schemas/session_start.json`
- [ ] `complete_session()` ← command `ai_setup_wizard.sessions.complete`  · schema `schemas/session_complete.json`
- [ ] `abandon_session()` ← command `ai_setup_wizard.sessions.abandon`  · schema `schemas/session_abandon.json`
- [ ] `add_question()` ← command `ai_setup_wizard.questions.add`  · schema `schemas/question_add.json`
- [ ] `apply_recommendation()` ← command `ai_setup_wizard.recommendations.apply`  · schema `schemas/recommendation_apply.json`

### `assistant`  (2)  ·  ver `assistant/WASM-TODO.md`
- [ ] `confirm_action()` ← command `assistant.actions.confirm`  · schema `schemas/action_confirm.json`
- [ ] `chat_send()` ← command `assistant.chat.send`

### `dashboards`  (2)  ·  ver `dashboards/WASM-TODO.md`
- [ ] `duplicate_dashboard()` ← command `dashboards.dashboards.duplicate`  · schema `schemas/dashboard_duplicate.json`
- [ ] `share_dashboard()` ← command `dashboards.shares.share`  · schema `schemas/share_dashboard.json`

### `kpis`  (1)  ·  ver `kpis/WASM-TODO.md`
- [ ] `record_value()` ← command `kpis.values.record`  · schema `schemas/value_record.json`

### `reports`  (1)  ·  ver `reports/WASM-TODO.md`
- [ ] `run_report()` ← command `reports.reports.run`  · schema `schemas/run_report.json`

### `forecasting`  (2)  ·  ver `forecasting/WASM-TODO.md`
- [ ] `run_forecast()` ← command `forecasting.forecasts.run`  · schema `schemas/forecast_run.json`
- [ ] `record_accuracy()` ← command `forecasting.forecasts.record_accuracy`  · schema `schemas/forecast_record_accuracy.json`

### `olap_cubes`  (3)  ·  ver `olap_cubes/WASM-TODO.md`
- [ ] `execute_query()` ← command `olap_cubes.query.execute`  · schema `schemas/query_execute.json`
- [ ] `cache_slice()` ← command `olap_cubes.cache.put`  · schema `schemas/cache_put.json`
- [ ] `get_cached_slice()` ← command `olap_cubes.cache.get`  · schema `schemas/cache_get.json`

## Ya implementados (referencia / plantilla)

- [x] `inventory` — `bulk_create`, `receive_stock`, `decrease_on_sale`  (`handler/src/lib.rs` + `dist/handler.wasm`)
- [x] `customers` — `bulk_create`, `set_groups`, `set_tags`  (`handler/src/lib.rs` + `dist/handler.wasm`)
- [x] `sales` — `complete_sale`  (`handler/src/lib.rs` + `dist/handler.wasm`)
- [x] `invoice` — `create_invoice`, `create_from_sale`  (`handler/src/lib.rs` + `dist/handler.wasm`)
- [x] `cash_register` — `add_count`, `record_sale`  (`handler/src/lib.rs` + `dist/handler.wasm`)
