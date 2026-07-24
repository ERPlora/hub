import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { isLegacyBackupsHash, resolveSystemTab, SYSTEM_TABS } from './system-tabs';

const source = readFileSync(new URL('../views/SystemPage.vue', import.meta.url), 'utf8');
const contract = readFileSync(new URL('./system.ts', import.meta.url), 'utf8');

describe('navegación de Sistema', () => {
  it('reserva Sistema para diagnóstico y retira la pestaña duplicada de copias', () => {
    expect(SYSTEM_TABS).toEqual(['resources', 'updates', 'documents', 'logs']);
    expect(source).not.toContain('value="backups"');
    expect(source).not.toContain("tab === 'backups'");
    expect(contract).not.toContain('backups?:');
  });

  it('reconoce el enlace antiguo para redirigirlo a Ajustes → Datos', () => {
    expect(isLegacyBackupsHash('#backups')).toBe(true);
    expect(resolveSystemTab('#backups')).toBe('resources');
  });
});
