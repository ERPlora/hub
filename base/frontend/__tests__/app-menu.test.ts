import { describe, expect, it } from 'vitest';

import { appMenu, menuOf } from './app-menu';

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
  it('reads every entry of the navigation in order, by position or by name, with the permission that opens it', () => {
    expect(menuOf(SOURCE)).toEqual([
      { id: 'items', icon: 'ion:cube-outline', path: '/stock/items', permission: 'stock.view' },
      { id: 'history', icon: 'ion:time-outline', path: '/stock/history', permission: 'stock.view_log' },
      { id: 'settings', icon: 'ion:settings-outline', path: '/stock/settings', permission: 'stock.manage' },
      { id: 'bare', icon: 'ion:list-outline', path: '/stock/bare', permission: undefined },
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
