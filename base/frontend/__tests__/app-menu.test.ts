import { describe, expect, it } from 'vitest';

import { appMenu, menuOf, openMenu, withFirstEntries, withMenu } from './app-menu';

const SOURCE = `
class StockConfig(LiveAppConfig):
    navigation = [
        Nav("items", _("Items"), "ion:cube-outline", "/stock/items", permission="stock.view"),
        Nav(
            "history", pgettext_lazy("stock menu", "History, (all)"), "ion:time-outline", "/stock/history",
            permission="stock.view_log",
        ),
        Nav(
            id="settings",
            label=_("Settings"),
            icon="ion:settings-outline",
            path="/stock/settings",
            permission="stock.manage",
        ),
        Nav("bare", _("Bare"), "ion:list-outline", "/stock/bare")
    ]
    bell = [BellCounter(key="low", operation="stock.item.low", route="/stock/low", label=_("Low"))]
`;

describe('menuOf', () => {
  it('reads every entry of the navigation in order, by position or by name, with its English label and the permission that opens it', () => {
    expect(menuOf(SOURCE)).toEqual([
      { id: 'items', label: 'Items', icon: 'ion:cube-outline', path: '/stock/items', permission: 'stock.view' },
      {
        id: 'history',
        label: 'History, (all)',
        icon: 'ion:time-outline',
        path: '/stock/history',
        permission: 'stock.view_log',
      },
      {
        id: 'settings',
        label: 'Settings',
        icon: 'ion:settings-outline',
        path: '/stock/settings',
        permission: 'stock.manage',
      },
      { id: 'bare', label: 'Bare', icon: 'ion:list-outline', path: '/stock/bare', permission: undefined },
    ]);
  });

  it('reads nothing but the navigation: a path the bell names is no entry', () => {
    expect(menuOf(SOURCE).map((entry) => entry.path)).not.toContain('/stock/low');
  });

  it('reads no menu from an app without navigation', () => {
    expect(menuOf('class ReportsConfig(LiveAppConfig):\n    label = "reports"\n')).toEqual([]);
  });
});

describe('appMenu', () => {
  it("reads the menu of one of the Hub's apps from its apps.py", () => {
    const menu = appMenu('tax');
    expect(menu.map((entry) => entry.path)).toEqual(['/tax/categories', '/tax/rules', '/tax/aliases', '/tax/settings']);
    expect(menu.map((entry) => entry.permission)).toEqual(['tax.manage', 'tax.manage', 'tax.manage', 'tax.manage']);
  });
});

describe('openMenu', () => {
  it("is the menu base.session.me gives whoever holds `permissions`: the app's name and the entries they open, in order", () => {
    expect(openMenu('tax', ['tax.manage'])).toEqual([
      {
        id: 'tax',
        label: 'Taxes',
        items: [
          { path: '/tax/categories', label: 'Categories', icon: 'ion:pricetags-outline' },
          { path: '/tax/rules', label: 'Rules', icon: 'ion:receipt-outline' },
          { path: '/tax/aliases', label: 'Aliases', icon: 'ion:swap-horizontal-outline' },
          { path: '/tax/settings', label: 'Settings', icon: 'ion:settings-outline' },
        ],
      },
    ]);
  });

  it('leaves out each entry whose permission the person lacks', () => {
    const [kitchen] = openMenu('kitchen', ['kitchen.view_ticket', 'kitchen.view_log']);
    expect(kitchen.items.map((item) => item.path)).toEqual(['/kitchen/display', '/kitchen/tickets', '/kitchen/history']);
  });

  it("opens every entry to the superuser's wildcard", () => {
    expect(openMenu('payment', ['*'])[0].items.map((item) => item.path)).toEqual(['/payment/payments', '/payment/methods']);
  });

  it('has no section for an app none of whose entries the person opens, as the server leaves it out', () => {
    expect(openMenu('tax', ['sale.add_sale'])).toEqual([]);
  });
});

describe('withMenu', () => {
  it("gives a test's person the menu its own permissions open, whatever menu it was copied with", () => {
    const owner = { user: { id: '1', label: 'Ana' }, permissions: ['tax.manage'], menu: [], apps: [], language: 'en' };
    expect(withMenu('tax', owner).menu).toEqual(openMenu('tax', ['tax.manage']));
    expect(withMenu('tax', { ...withMenu('tax', owner), permissions: [] }).menu).toEqual([]);
    expect(withMenu('tax', owner).permissions).toEqual(['tax.manage']);
  });
});

describe('withFirstEntries', () => {
  it("leaves open only the first `count` entries of the person's menu, whatever its permissions", () => {
    const owner = withMenu('tax', { user: { id: '1', label: 'Ana' }, permissions: ['tax.manage'], menu: [], apps: [], language: 'en' });
    const cut = withFirstEntries(owner, 2);
    expect(cut.menu[0].items.map((item) => item.path)).toEqual(['/tax/categories', '/tax/rules']);
    expect(cut.menu[0].label).toBe('Taxes');
    expect(cut.permissions).toEqual(['tax.manage']);
    expect(owner.menu[0].items).toHaveLength(4);
  });
});
