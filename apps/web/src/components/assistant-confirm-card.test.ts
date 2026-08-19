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

// hub#1040 — la tarjeta deja de hablar en lenguaje de máquina.
//
// Enseñaba `subHeader: name` (el nombre crudo de la tool, sin traducir) y `message` = el
// `JSON.stringify` de los argumentos. El dueño aprobaba `{"price_cents": 1500}` sin leer nunca
// «15,00 €» — en el último punto donde un humano puede cazar un ×100.
describe('la tarjeta se lee en palabras del negocio (hub#1040)', () => {
  it('ya no imprime el nombre crudo de la tool como subtítulo', () => {
    expect(drawer).not.toContain('subHeader: name');
  });

  it('ya no vuelca el JSON de los argumentos', () => {
    expect(drawer).not.toMatch(/message:\s*pretty/);
  });

  it('describe la llamada con el helper que formatea el dinero', () => {
    expect(drawer).toContain('describeToolCall');
  });

  it('le pasa las marcas de dinero que mandó el runtime', () => {
    expect(drawer).toContain('moneyFields');
  });
});
