// The op → route map the SDK's API client uses. Written by hand for the PoC (V3 generates it from
// `/api/openapi.json`); these cases pin the routes the shell and the demo depend on.
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from './operation-routes';

describe('OPERATION_ROUTES', () => {
  it('binds base.session.me to GET /api/me (base/api.py)', () => {
    expect(OPERATION_ROUTES['base.session.me']).toEqual({ method: 'get', path: '/api/me' });
  });

  it('binds the seven demo operations, one input each: no path parameters, the id in the query or the body', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'demo.item.list': { method: 'get', path: '/api/demo/items' },
      'demo.item.detail': { method: 'get', path: '/api/demo/items/detail' },
      'demo.item.stats': { method: 'get', path: '/api/demo/items/stats' },
      'demo.item.create': { method: 'post', path: '/api/demo/items' },
      'demo.item.update': { method: 'post', path: '/api/demo/items/update' },
      'demo.item.delete': { method: 'post', path: '/api/demo/items/delete' },
      'demo.item.add_line': { method: 'post', path: '/api/demo/items/add_line' },
    });
  });

  it('binds the eighteen tax operations to apps/tax/api.py: queries by GET, commands by POST', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'tax.category.list': { method: 'get', path: '/api/tax/categories' },
      'tax.category.get': { method: 'get', path: '/api/tax/categories/detail' },
      'tax.category.create': { method: 'post', path: '/api/tax/categories' },
      'tax.rule.list': { method: 'get', path: '/api/tax/rules' },
      'tax.rule.status': { method: 'get', path: '/api/tax/rules/status' },
      'tax.rule.parent_candidates': { method: 'get', path: '/api/tax/rules/parent_candidates' },
      'tax.rule.countries': { method: 'get', path: '/api/tax/rules/countries' },
      'tax.rule.create': { method: 'post', path: '/api/tax/rules' },
      'tax.rule.bulk_create': { method: 'post', path: '/api/tax/rules/bulk_create' },
      'tax.rule.end': { method: 'post', path: '/api/tax/rules/end' },
      'tax.rule.deactivate': { method: 'post', path: '/api/tax/rules/deactivate' },
      'tax.rule.activate': { method: 'post', path: '/api/tax/rules/activate' },
      'tax.alias.list': { method: 'get', path: '/api/tax/aliases' },
      'tax.alias.resolve': { method: 'get', path: '/api/tax/aliases/resolve' },
      'tax.alias.create': { method: 'post', path: '/api/tax/aliases' },
      'tax.rate.calculate': { method: 'get', path: '/api/tax/rates/calculate' },
      // The business's tax region (TAX-F11).
      'tax.settings.get': { method: 'get', path: '/api/tax/settings' },
      'tax.settings.update': { method: 'post', path: '/api/tax/settings' },
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('tax.'))).toHaveLength(18);
  });

  it('binds the twenty-six routed inventory operations to apps/inventory/api.py (the two sale reactions have no route)', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'inventory.product.list': { method: 'get', path: '/api/inventory/products' },
      'inventory.product.get': { method: 'get', path: '/api/inventory/products/detail' },
      'inventory.product.list_for_sale': { method: 'get', path: '/api/inventory/products/for_sale' },
      'inventory.product.list_low_stock': { method: 'get', path: '/api/inventory/products/low_stock' },
      'inventory.product.export': { method: 'get', path: '/api/inventory/products/export' },
      'inventory.product.create': { method: 'post', path: '/api/inventory/products' },
      'inventory.product.bulk_create': { method: 'post', path: '/api/inventory/products/bulk_create' },
      'inventory.product.update': { method: 'post', path: '/api/inventory/products/update' },
      'inventory.product.delete': { method: 'post', path: '/api/inventory/products/delete' },
      'inventory.product_category.list': { method: 'get', path: '/api/inventory/product_categories' },
      'inventory.product_category.add': { method: 'post', path: '/api/inventory/product_categories/add' },
      'inventory.product_category.remove': { method: 'post', path: '/api/inventory/product_categories/remove' },
      'inventory.category.list': { method: 'get', path: '/api/inventory/categories' },
      'inventory.category.export': { method: 'get', path: '/api/inventory/categories/export' },
      'inventory.category.create': { method: 'post', path: '/api/inventory/categories' },
      'inventory.category.bulk_create': { method: 'post', path: '/api/inventory/categories/bulk_create' },
      'inventory.category.update': { method: 'post', path: '/api/inventory/categories/update' },
      'inventory.category.delete': { method: 'post', path: '/api/inventory/categories/delete' },
      'inventory.movement.list': { method: 'get', path: '/api/inventory/movements' },
      'inventory.stock.get_summary': { method: 'get', path: '/api/inventory/stock/summary' },
      'inventory.stock.receive': { method: 'post', path: '/api/inventory/stock/receive' },
      'inventory.stock.count': { method: 'post', path: '/api/inventory/stock/count' },
      'inventory.stock.write_off': { method: 'post', path: '/api/inventory/stock/write_off' },
      'inventory.unit.list': { method: 'get', path: '/api/inventory/units' },
      'inventory.config.get': { method: 'get', path: '/api/inventory/config' },
      'inventory.config.update': { method: 'post', path: '/api/inventory/config' },
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('inventory.'))).toHaveLength(26);
  });

  it('binds the 41 customer operations that have a route (apps/customer/api.py); purchase.record/void are the system\'s', () => {
    const customer = Object.fromEntries(Object.entries(OPERATION_ROUTES).filter(([op]) => op.startsWith('customer.')));
    expect(customer).toEqual({
      'customer.customer.list': { method: 'get', path: '/api/customer/customers' },
      'customer.customer.detail': { method: 'get', path: '/api/customer/customers/detail' },
      'customer.customer.stats': { method: 'get', path: '/api/customer/customers/stats' },
      'customer.customer.by_phone': { method: 'get', path: '/api/customer/customers/by_phone' },
      'customer.customer.export': { method: 'get', path: '/api/customer/customers/export' },
      'customer.customer.create': { method: 'post', path: '/api/customer/customers' },
      'customer.customer.update': { method: 'post', path: '/api/customer/customers/update' },
      'customer.customer.import': { method: 'post', path: '/api/customer/customers/import' },
      'customer.customer.set_groups': { method: 'post', path: '/api/customer/customers/set_groups' },
      'customer.customer.set_tags': { method: 'post', path: '/api/customer/customers/set_tags' },
      'customer.customer.delete': { method: 'post', path: '/api/customer/customers/delete' },
      'customer.customer.merge': { method: 'post', path: '/api/customer/customers/merge' },
      'customer.customer.erase': { method: 'post', path: '/api/customer/customers/erase' },
      'customer.group.list': { method: 'get', path: '/api/customer/groups' },
      'customer.group.create': { method: 'post', path: '/api/customer/groups' },
      'customer.group.update': { method: 'post', path: '/api/customer/groups/update' },
      'customer.group.delete': { method: 'post', path: '/api/customer/groups/delete' },
      'customer.tag.list': { method: 'get', path: '/api/customer/tags' },
      'customer.tag.create': { method: 'post', path: '/api/customer/tags' },
      'customer.tag.update': { method: 'post', path: '/api/customer/tags/update' },
      'customer.tag.delete': { method: 'post', path: '/api/customer/tags/delete' },
      'customer.field.list': { method: 'get', path: '/api/customer/fields' },
      'customer.field.create': { method: 'post', path: '/api/customer/fields' },
      'customer.field.update': { method: 'post', path: '/api/customer/fields/update' },
      'customer.field.delete': { method: 'post', path: '/api/customer/fields/delete' },
      'customer.activity.list': { method: 'get', path: '/api/customer/activity' },
      'customer.activity.add': { method: 'post', path: '/api/customer/activity' },
      'customer.note.add': { method: 'post', path: '/api/customer/notes' },
      'customer.purchase.list': { method: 'get', path: '/api/customer/purchases' },
      'customer.purchase.divergences': { method: 'get', path: '/api/customer/purchases/divergences' },
      'customer.consent.history': { method: 'get', path: '/api/customer/consents' },
      'customer.consent.state': { method: 'get', path: '/api/customer/consents/state' },
      'customer.consent.grant': { method: 'post', path: '/api/customer/consents/grant' },
      'customer.consent.withdraw': { method: 'post', path: '/api/customer/consents/withdraw' },
      // CUSTOMER-F32: the health data, screen only (no assistant tool, no API key: GDPR art. 9).
      'customer.health.detail': { method: 'get', path: '/api/customer/health' },
      'customer.health.grant': { method: 'post', path: '/api/customer/health/grant' },
      'customer.health.withdraw': { method: 'post', path: '/api/customer/health/withdraw' },
      'customer.health.update': { method: 'post', path: '/api/customer/health/update' },
      'customer.order.list': { method: 'get', path: '/api/customer/orders' },
      'customer.order.customer': { method: 'get', path: '/api/customer/orders/customer' },
      'customer.order.link': { method: 'post', path: '/api/customer/orders/link' },
    });
  });

  it('binds the 33 staff operations to apps/staff/api.py: queries by GET, commands by POST', () => {
    const staff = Object.fromEntries(Object.entries(OPERATION_ROUTES).filter(([op]) => op.startsWith('staff.')));
    expect(staff).toEqual({
      'staff.member.list': { method: 'get', path: '/api/staff/members' },
      'staff.member.detail': { method: 'get', path: '/api/staff/members/detail' },
      'staff.member.mine': { method: 'get', path: '/api/staff/members/mine' },
      'staff.member.compensation': { method: 'get', path: '/api/staff/members/compensation' },
      'staff.member.stats': { method: 'get', path: '/api/staff/members/stats' },
      'staff.member.create': { method: 'post', path: '/api/staff/members' },
      'staff.member.bulk_create': { method: 'post', path: '/api/staff/members/bulk_create' },
      'staff.member.update': { method: 'post', path: '/api/staff/members/update' },
      'staff.member.deactivate': { method: 'post', path: '/api/staff/members/deactivate' },
      'staff.member.terminate': { method: 'post', path: '/api/staff/members/terminate' },
      'staff.commission.summary': { method: 'get', path: '/api/staff/commissions' },
      'staff.account.list': { method: 'get', path: '/api/staff/accounts' },
      'staff.role.list': { method: 'get', path: '/api/staff/roles' },
      'staff.role.create': { method: 'post', path: '/api/staff/roles' },
      'staff.role.update': { method: 'post', path: '/api/staff/roles/update' },
      'staff.schedule.list': { method: 'get', path: '/api/staff/schedules' },
      'staff.schedule.detail': { method: 'get', path: '/api/staff/schedules/detail' },
      'staff.schedule.create': { method: 'post', path: '/api/staff/schedules' },
      'staff.schedule.update': { method: 'post', path: '/api/staff/schedules/update' },
      'staff.schedule.set_active': { method: 'post', path: '/api/staff/schedules/set_active' },
      'staff.schedule.delete': { method: 'post', path: '/api/staff/schedules/delete' },
      'staff.availability.for_member': { method: 'get', path: '/api/staff/availability' },
      'staff.time_off.list': { method: 'get', path: '/api/staff/time_off' },
      'staff.time_off.detail': { method: 'get', path: '/api/staff/time_off/detail' },
      'staff.time_off.today': { method: 'get', path: '/api/staff/time_off/today' },
      'staff.time_off.mine': { method: 'get', path: '/api/staff/time_off/mine' },
      'staff.time_off.create': { method: 'post', path: '/api/staff/time_off' },
      'staff.time_off.request': { method: 'post', path: '/api/staff/time_off/request' },
      'staff.time_off.approve': { method: 'post', path: '/api/staff/time_off/approve' },
      'staff.time_off.reject': { method: 'post', path: '/api/staff/time_off/reject' },
      'staff.time_off.cancel': { method: 'post', path: '/api/staff/time_off/cancel' },
      'staff.settings.get': { method: 'get', path: '/api/staff/settings' },
      'staff.settings.update': { method: 'post', path: '/api/staff/settings' },
    });
  });

  it('binds the 54 routed sale operations to apps/sale/api.py: queries by GET, commands by POST; the reaction to a merge has no route', () => {
    const sale = Object.fromEntries(Object.entries(OPERATION_ROUTES).filter(([op]) => op.startsWith('sale.')));
    expect(sale).toEqual({
      'sale.sale.list': { method: 'get', path: '/api/sale/sales' },
      'sale.sale.complete': { method: 'post', path: '/api/sale/sales' },
      'sale.sale.get': { method: 'get', path: '/api/sale/sales/detail' },
      'sale.sale.by_idempotency_key': { method: 'get', path: '/api/sale/sales/by_key' },
      'sale.sale.stats': { method: 'get', path: '/api/sale/sales/stats' },
      'sale.sale.today': { method: 'get', path: '/api/sale/sales/today' },
      'sale.sale.last_7_days': { method: 'get', path: '/api/sale/sales/last_7_days' },
      'sale.sale.by_staff': { method: 'get', path: '/api/sale/sales/by_staff' },
      'sale.sale.tax_kind': { method: 'get', path: '/api/sale/sales/tax_kind' },
      'sale.sale.complete_over_limit': { method: 'post', path: '/api/sale/sales/complete_over_limit' },
      'sale.sale.void': { method: 'post', path: '/api/sale/sales/void' },
      'sale.sale.refund': { method: 'post', path: '/api/sale/sales/refund' },
      'sale.sale.issue_documents': { method: 'post', path: '/api/sale/sales/issue_documents' },
      'sale.checkout.preview': { method: 'get', path: '/api/sale/checkout/preview' },
      'sale.order.list': { method: 'get', path: '/api/sale/orders' },
      'sale.order.open': { method: 'post', path: '/api/sale/orders' },
      'sale.order.get': { method: 'get', path: '/api/sale/orders/detail' },
      'sale.order.add_line': { method: 'post', path: '/api/sale/orders/add_line' },
      'sale.order.add_open_line': { method: 'post', path: '/api/sale/orders/add_open_line' },
      'sale.order.add_service_line': { method: 'post', path: '/api/sale/orders/add_service_line' },
      'sale.order.apply_voucher': { method: 'post', path: '/api/sale/orders/apply_voucher' },
      'sale.order.remove_voucher': { method: 'post', path: '/api/sale/orders/remove_voucher' },
      'sale.order.update_line': { method: 'post', path: '/api/sale/orders/update_line' },
      'sale.order.set_line_staff': { method: 'post', path: '/api/sale/orders/set_line_staff' },
      'sale.order.split_line': { method: 'post', path: '/api/sale/orders/split_line' },
      'sale.order.remove_line': { method: 'post', path: '/api/sale/orders/remove_line' },
      'sale.order.void_line': { method: 'post', path: '/api/sale/orders/void_line' },
      'sale.order.fire': { method: 'post', path: '/api/sale/orders/fire' },
      'sale.order.split': { method: 'post', path: '/api/sale/orders/split' },
      'sale.order.merge': { method: 'post', path: '/api/sale/orders/merge' },
      'sale.order.void': { method: 'post', path: '/api/sale/orders/void' },
      'sale.order.set_discount': { method: 'post', path: '/api/sale/orders/set_discount' },
      'sale.order.set_discount_over_limit': { method: 'post', path: '/api/sale/orders/set_discount_over_limit' },
      'sale.order.set_line_discount': { method: 'post', path: '/api/sale/orders/set_line_discount' },
      'sale.order.set_line_discount_over_limit': { method: 'post', path: '/api/sale/orders/set_line_discount_over_limit' },
      'sale.order.set_label': { method: 'post', path: '/api/sale/orders/set_label' },
      'sale.order.set_appointment': { method: 'post', path: '/api/sale/orders/set_appointment' },
      'sale.payment_method.list': { method: 'get', path: '/api/sale/payment_methods' },
      'sale.payment_method.create': { method: 'post', path: '/api/sale/payment_methods' },
      'sale.settings.get': { method: 'get', path: '/api/sale/settings' },
      'sale.settings.update': { method: 'post', path: '/api/sale/settings' },
      'sale.pos_settings.get': { method: 'get', path: '/api/sale/pos_settings' },
      'sale.department.list': { method: 'get', path: '/api/sale/departments' },
      'sale.department.create': { method: 'post', path: '/api/sale/departments' },
      'sale.department.update': { method: 'post', path: '/api/sale/departments/update' },
      'sale.department.delete': { method: 'post', path: '/api/sale/departments/delete' },
      'sale.quick_note.list': { method: 'get', path: '/api/sale/quick_notes' },
      'sale.quick_note.create': { method: 'post', path: '/api/sale/quick_notes' },
      'sale.quick_note.update': { method: 'post', path: '/api/sale/quick_notes/update' },
      'sale.quick_note.delete': { method: 'post', path: '/api/sale/quick_notes/delete' },
      'sale.business_day.get': { method: 'get', path: '/api/sale/business_day' },
      'sale.refund.list': { method: 'get', path: '/api/sale/refunds' },
      'sale.refund.options': { method: 'get', path: '/api/sale/refunds/options' },
      'sale.refund.by_idempotency_key': { method: 'get', path: '/api/sale/refunds/by_key' },
    });
  });

  it('binds the thirty-seven routed service operations to apps/service/api.py (the reactions and the sessions of the till have no route)', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'service.service.list': { method: 'get', path: '/api/service/services' },
      'service.service.create': { method: 'post', path: '/api/service/services' },
      'service.service.get': { method: 'get', path: '/api/service/services/detail' },
      'service.service.list_for_sale': { method: 'get', path: '/api/service/services/for_sale' },
      'service.service.bulk_create': { method: 'post', path: '/api/service/services/bulk_create' },
      'service.service.update': { method: 'post', path: '/api/service/services/update' },
      'service.service.archive': { method: 'post', path: '/api/service/services/archive' },
      'service.service.restore': { method: 'post', path: '/api/service/services/restore' },
      'service.catalog.status': { method: 'get', path: '/api/service/catalog/status' },
      'service.category.list': { method: 'get', path: '/api/service/categories' },
      'service.category.create': { method: 'post', path: '/api/service/categories' },
      'service.category.get': { method: 'get', path: '/api/service/categories/detail' },
      'service.category.update': { method: 'post', path: '/api/service/categories/update' },
      'service.category.delete': { method: 'post', path: '/api/service/categories/delete' },
      'service.settings.get': { method: 'get', path: '/api/service/settings' },
      'service.settings.update': { method: 'post', path: '/api/service/settings' },
      'service.assignment.list': { method: 'get', path: '/api/service/assignments' },
      'service.assignment.eligible': { method: 'get', path: '/api/service/assignments/eligible' },
      'service.assignment.assign': { method: 'post', path: '/api/service/assignments/assign' },
      'service.assignment.update': { method: 'post', path: '/api/service/assignments/update' },
      'service.assignment.remove': { method: 'post', path: '/api/service/assignments/remove' },
      'service.package.list': { method: 'get', path: '/api/service/packages' },
      'service.package.create': { method: 'post', path: '/api/service/packages' },
      'service.package.get': { method: 'get', path: '/api/service/packages/detail' },
      'service.package.update': { method: 'post', path: '/api/service/packages/update' },
      'service.package.delete': { method: 'post', path: '/api/service/packages/delete' },
      'service.grant.list': { method: 'get', path: '/api/service/grants' },
      'service.grant.create': { method: 'post', path: '/api/service/grants' },
      'service.grant.list_orphans': { method: 'get', path: '/api/service/grants/orphans' },
      'service.grant.void_check': { method: 'get', path: '/api/service/grants/void_check' },
      'service.grant.adjust_check': { method: 'get', path: '/api/service/grants/adjust_check' },
      'service.grant.redeem_check': { method: 'get', path: '/api/service/grants/redeem_check' },
      'service.grant.tender_options': { method: 'get', path: '/api/service/grants/tender_options' },
      'service.grant.void': { method: 'post', path: '/api/service/grants/void' },
      'service.grant.adjust': { method: 'post', path: '/api/service/grants/adjust' },
      'service.grant.redeem': { method: 'post', path: '/api/service/grants/redeem' },
      'service.movement.list': { method: 'get', path: '/api/service/movements' },
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('service.'))).toHaveLength(37);
  });

  it('binds the sixteen cash register operations to apps/cash_register/api.py: queries by GET, commands by POST', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'cash_register.settings.get': { method: 'get', path: '/api/cash_register/settings' },
      'cash_register.settings.update': { method: 'post', path: '/api/cash_register/settings' },
      'cash_register.register.list': { method: 'get', path: '/api/cash_register/registers' },
      'cash_register.register.create': { method: 'post', path: '/api/cash_register/registers' },
      'cash_register.register.update': { method: 'post', path: '/api/cash_register/registers/update' },
      'cash_register.session.list': { method: 'get', path: '/api/cash_register/sessions' },
      'cash_register.session.current': { method: 'get', path: '/api/cash_register/sessions/current' },
      'cash_register.session.get': { method: 'get', path: '/api/cash_register/sessions/detail' },
      'cash_register.session.open': { method: 'post', path: '/api/cash_register/sessions/open' },
      'cash_register.session.close': { method: 'post', path: '/api/cash_register/sessions/close' },
      'cash_register.session.auto_close': { method: 'post', path: '/api/cash_register/sessions/auto_close' },
      'cash_register.movement.list': { method: 'get', path: '/api/cash_register/movements' },
      'cash_register.movement.add': { method: 'post', path: '/api/cash_register/movements' },
      'cash_register.count.list': { method: 'get', path: '/api/cash_register/counts' },
      'cash_register.count.add': { method: 'post', path: '/api/cash_register/counts' },
      'cash_register.currency.get': { method: 'get', path: '/api/cash_register/currency' },
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('cash_register.'))).toHaveLength(16);
  });

  it('binds the twenty routed invoice operations to apps/invoice/api.py (issuer.sync is the system\'s)', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'invoice.invoice.list': { method: 'get', path: '/api/invoice/invoices' },
      'invoice.invoice.get': { method: 'get', path: '/api/invoice/invoices/detail' },
      'invoice.invoice.by_source': { method: 'get', path: '/api/invoice/invoices/by_source' },
      'invoice.invoice.document': { method: 'get', path: '/api/invoice/invoices/document' },
      'invoice.invoice.line_defaults': { method: 'get', path: '/api/invoice/invoices/line_defaults' },
      'invoice.invoice.create': { method: 'post', path: '/api/invoice/invoices' },
      'invoice.invoice.create_from_sale': { method: 'post', path: '/api/invoice/invoices/from_sale' },
      'invoice.invoice.substitute': { method: 'post', path: '/api/invoice/invoices/substitute' },
      'invoice.invoice.mark_paid': { method: 'post', path: '/api/invoice/invoices/mark_paid' },
      'invoice.invoice.rectify': { method: 'post', path: '/api/invoice/invoices/rectify' },
      'invoice.invoice.rectify_from_refund': { method: 'post', path: '/api/invoice/invoices/rectify_from_refund' },
      'invoice.invoice.rectify_from_void': { method: 'post', path: '/api/invoice/invoices/rectify_from_void' },
      'invoice.series.list': { method: 'get', path: '/api/invoice/series' },
      'invoice.series.peek_next': { method: 'get', path: '/api/invoice/series/peek_next' },
      'invoice.series.create': { method: 'post', path: '/api/invoice/series' },
      'invoice.series.update': { method: 'post', path: '/api/invoice/series/update' },
      'invoice.numbering.status': { method: 'get', path: '/api/invoice/numbering/status' },
      'invoice.numbering.gaps': { method: 'get', path: '/api/invoice/numbering/gaps' },
      'invoice.numbering.allocations': { method: 'get', path: '/api/invoice/numbering/allocations' },
      'invoice.issuer.get': { method: 'get', path: '/api/invoice/issuer' },
      'invoice.issuer.update': { method: 'post', path: '/api/invoice/issuer' },
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('invoice.'))).toHaveLength(21);
  });

  it('names every operation <app>.<entity>.<action> and keeps every route under /api/', () => {
    for (const [op, route] of Object.entries(OPERATION_ROUTES)) {
      expect(op).toMatch(/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/);
      expect(route.path).toMatch(/^\/api\//);
      // ninja's parity binds one parameter (the operation's input): no `{param}` next to a body.
      expect(route.path).not.toMatch(/[{}]/);
    }
  });
});

describe('the voucher at the till (SALE-F27, SERVICE-F22)', () => {
  it('reads the vouchers that can pay a line from apps/service/api.py and pays it through apps/sale/api.py', () => {
    expect(OPERATION_ROUTES['service.grant.tender_options']).toEqual({ method: 'get', path: '/api/service/grants/tender_options' });
    expect(OPERATION_ROUTES['sale.order.apply_voucher']).toEqual({ method: 'post', path: '/api/sale/orders/apply_voucher' });
    // Services' session commands run inside Sales' writes: no route.
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('service.session.'))).toEqual([]);
  });
});

describe('the payment app (apps/payment/api.py)', () => {
  it('binds its thirteen operations: queries by GET, commands by POST', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'payment.payment.list': { method: 'get', path: '/api/payment/payments' },
      'payment.payment.get': { method: 'get', path: '/api/payment/payments/detail' },
      'payment.payment.create': { method: 'post', path: '/api/payment/payments' },
      'payment.payment.approve': { method: 'post', path: '/api/payment/payments/approve' },
      'payment.payment.mark_sent': { method: 'post', path: '/api/payment/payments/mark_sent' },
      'payment.payment.mark_completed': { method: 'post', path: '/api/payment/payments/mark_completed' },
      'payment.payment.cancel': { method: 'post', path: '/api/payment/payments/cancel' },
      'payment.method.list': { method: 'get', path: '/api/payment/methods' },
      'payment.method.get': { method: 'get', path: '/api/payment/methods/detail' },
      'payment.method.create': { method: 'post', path: '/api/payment/methods' },
      'payment.method.update': { method: 'post', path: '/api/payment/methods/update' },
      'payment.method.deactivate': { method: 'post', path: '/api/payment/methods/deactivate' },
      'payment.method.activate': { method: 'post', path: '/api/payment/methods/activate' },
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('payment.'))).toHaveLength(13);
  });
});
