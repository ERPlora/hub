// La confirm-card EXISTE en el drawer (hub#631): sin `onConfirm`, streamAssistant cancela toda
// mutación por default-deny — seguro, pero deja al asistente sin manos (ni instalar un módulo ni
// ningún command de módulo) y el modelo se inventa políticas para explicarlo. Mismo patrón de
// test contractual que assistant-reads-the-query.test.ts: el contrato se afirma sobre el fuente.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const drawer = readFileSync(new URL('./AssistantDrawer.vue', import.meta.url), 'utf8');

describe('assistant confirm card', () => {
  it('el drawer pasa onConfirm a streamAssistant (sin él, default-deny cancela todo command)', () => {
    expect(drawer).toContain('onConfirm:');
  });
  it('la confirmación es un ion-alert nativo con las claves i18n del asistente', () => {
    expect(drawer).toContain('alertController');
    for (const key of ['assistant.confirmTitle', 'assistant.confirmCancel', 'assistant.confirmRun']) {
      expect(drawer).toContain(key);
    }
  });
});
