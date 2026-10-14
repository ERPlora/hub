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

  it('binds the sixteen tax operations to apps/tax/api.py: queries by GET, commands by POST', () => {
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
    });
    expect(Object.keys(OPERATION_ROUTES).filter((op) => op.startsWith('tax.'))).toHaveLength(16);
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

  it('binds the 37 customer operations that have a route (apps/customer/api.py); purchase.record/void are the system\'s', () => {
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

  it('binds the 49 routed sale operations to apps/sale/api.py: queries by GET, commands by POST; the reaction to a merge has no route', () => {
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
      'sale.sale.complete_over_limit': { method: 'post', path: '/api/sale/sales/complete_over_limit' },
      'sale.sale.void': { method: 'post', path: '/api/sale/sales/void' },
      'sale.sale.refund': { method: 'post', path: '/api/sale/sales/refund' },
      'sale.checkout.preview': { method: 'get', path: '/api/sale/checkout/preview' },
      'sale.order.list': { method: 'get', path: '/api/sale/orders' },
      'sale.order.open': { method: 'post', path: '/api/sale/orders' },
      'sale.order.get': { method: 'get', path: '/api/sale/orders/detail' },
      'sale.order.add_line': { method: 'post', path: '/api/sale/orders/add_line' },
      'sale.order.add_open_line': { method: 'post', path: '/api/sale/orders/add_open_line' },
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

  it('names every operation <app>.<entity>.<action> and keeps every route under /api/', () => {
    for (const [op, route] of Object.entries(OPERATION_ROUTES)) {
      expect(op).toMatch(/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/);
      expect(route.path).toMatch(/^\/api\//);
      // ninja's parity binds one parameter (the operation's input): no `{param}` next to a body.
      expect(route.path).not.toMatch(/[{}]/);
    }
  });
});
