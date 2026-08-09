import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { isLegacyBackupsHash, resolveSystemTab, SYSTEM_TABS } from './system-tabs';

const source = readFileSync(new URL('../views/SystemPage.vue', import.meta.url), 'utf8');
const contract = readFileSync(new URL('./system.ts', import.meta.url), 'utf8');

describe('navegación de Sistema', () => {
  it('reserva Sistema para diagnóstico, suma «Plan y límites» y retira copias y documentos', () => {
    // `plan` = telemetría de recursos vs límites del plan (ADR-0154). Va tras `resources`.
    // `documents` se retiró: los documentos del hub viven en /files (gestor de `media/`).
    expect(SYSTEM_TABS).toEqual(['resources', 'plan', 'updates', 'logs']);
    expect(source).not.toContain('value="backups"');
    expect(source).not.toContain("tab === 'backups'");
    expect(source).not.toContain('value="documents"');
    expect(source).not.toContain("tab === 'documents'");
    expect(contract).not.toContain('backups?:');
  });

  it('reconoce el enlace antiguo para redirigirlo a Ajustes → Datos', () => {
    expect(isLegacyBackupsHash('#backups')).toBe(true);
    expect(resolveSystemTab('#backups')).toBe('resources');
  });
});
