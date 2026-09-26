// hub#2204 — the «Go to» buttons under an assistant answer read «Ir a Cash_register › settings»:
// the module id with its first letter capitalised and the raw tab id. The owner never sees those
// identifiers anywhere else — the sidebar, the launcher and the tab bar all name the app and the
// screen in their language, from `/api/navigation` (ADR-0055). The button has to use the same names.
import { describe, expect, it } from 'vitest';

import { routeLabel } from './assistant-routes';
import type { ModuleNavItem } from './nav';

const messages: Record<string, string> = {
  'moduleSettings.tab': 'Ajustes',
  'nav.home': 'Inicio',
  'nav.employees': 'Empleados',
  'nav.settings': 'Ajustes',
  'nav.apps': 'Apps',
  'nav.system': 'Sistema',
  'nav.billing': 'Mi plan',
};
const t = (key: string): string => messages[key] ?? key;

const modules: ModuleNavItem[] = [
  {
    path: '/m/cash_register',
    label: 'Caja',
    icon: '',
    tabs: [
      { id: 'sessions', label: 'Sesiones' },
      { id: 'movements', label: 'Movimientos' },
    ],
  },
  { path: '/m/invoice', label: 'Facturación', icon: '', tabs: [{ id: 'settings', label: 'Configuración' }] },
];

describe('routeLabel — a screen is named as the shell names it (hub#2204)', () => {
  it('the app by its translated name and the synthetic settings tab as «Ajustes»', () => {
    expect(routeLabel('/m/cash_register/settings', { modules, t })).toBe('Caja › Ajustes');
  });

  it('a tab the module declares, by its own translated label', () => {
    expect(routeLabel('/m/cash_register/sessions', { modules, t })).toBe('Caja › Sesiones');
  });

  it('a module that declares its own settings tab keeps the name it gave it', () => {
    expect(routeLabel('/m/invoice/settings', { modules, t })).toBe('Facturación › Configuración');
  });

  it('the app alone when the path names no tab', () => {
    expect(routeLabel('/m/cash_register', { modules, t })).toBe('Caja');
  });

  // Navigation not loaded yet (or a module that is not in it): never the raw identifier with an
  // underscore — the id read as words is the least bad name there is.
  it('without the navigation, the id reads as words, never with its underscore', () => {
    const label = routeLabel('/m/cash_register/settings', { modules: [], t });

    expect(label).toBe('Cash register › Ajustes');
    expect(label).not.toContain('_');
  });

  it('an unknown tab id reads as words too', () => {
    expect(routeLabel('/m/cash_register/daily_close', { modules, t })).toBe('Caja › Daily close');
  });

  it('the shell screens by their menu name, with or without a section anchor', () => {
    expect(routeLabel('/dashboard', { modules, t })).toBe('Inicio');
    expect(routeLabel('/employees', { modules, t })).toBe('Empleados');
    expect(routeLabel('/settings#permissions', { modules, t })).toBe('Ajustes');
    expect(routeLabel('/billing', { modules, t })).toBe('Mi plan');
  });
});
