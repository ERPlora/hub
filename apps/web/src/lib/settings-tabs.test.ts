import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolveSettingsTab, SETTINGS_TABS } from './settings-tabs';

const settingsSource = readFileSync(new URL('../views/SettingsPage.vue', import.meta.url), 'utf8');
const profileSource = readFileSync(new URL('../views/ProfilePage.vue', import.meta.url), 'utf8');

describe('navegación de Ajustes', () => {
  it('no ofrece una pestaña Tienda duplicada', () => {
    expect(SETTINGS_TABS).toEqual(['hub', 'tax', 'tickets', 'permissions', 'data']);
    expect(SETTINGS_TABS).not.toContain('store');
  });

  it('redirige el enlace antiguo de Tienda a los ajustes del Hub', () => {
    expect(resolveSettingsTab('#store')).toBe('hub');
    expect(resolveSettingsTab('#hub')).toBe('hub');
  });

  it('conserva los enlaces de las pestañas vigentes', () => {
    expect(resolveSettingsTab('#tax')).toBe('tax');
    expect(resolveSettingsTab('#tickets')).toBe('tickets');
    expect(resolveSettingsTab('#permissions')).toBe('permissions');
    expect(resolveSettingsTab('#data')).toBe('data');
  });

  it('mantiene exactamente una paleta global en Ajustes y una personal en Perfil', () => {
    expect(settingsSource.match(/<ok-theme-picker/g)).toHaveLength(1);
    expect(profileSource.match(/<ok-theme-picker/g)).toHaveLength(1);
  });

  it('no conserva el contenido ni el selector de la antigua Tienda', () => {
    expect(settingsSource).not.toContain("tab === 'store'");
    expect(settingsSource).not.toContain('value="store"');
    expect(settingsSource).not.toContain('storeType');
    expect(settingsSource).not.toContain('storeLocale');
  });

  it('does not show local-only Hub controls that pretend to save', () => {
    expect(settingsSource).not.toContain('hubTimezone');
    expect(settingsSource).not.toContain('showModulesInSidebar');
    expect(settingsSource).not.toContain('saveHubSettings');
    expect(settingsSource).toContain('country_code: value');
  });
});
