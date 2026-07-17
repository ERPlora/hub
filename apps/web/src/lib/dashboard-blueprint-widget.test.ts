// @vitest-environment happy-dom
// Contrato del widget CORE de puesta en marcha del hub (ADR-0113 §4). Tras la simplificación
// (decisión humano 2026-07-17): un ÚNICO CTA que aterriza en Ajustes › Datos. La primera vez
// nadie exporta configuración, así que el widget NO ofrece exportar — solo «configurar».
import { describe, it, expect, vi } from 'vitest';
import { buildBlueprintWidget } from './dashboard-blueprint-widget';

const t = (key: string): string => key;

describe('buildBlueprintWidget', () => {
  it('pinta título, cuerpo y UN solo CTA (sin botón de exportar)', () => {
    const cell = document.createElement('div');
    buildBlueprintWidget(cell, t, () => {});
    expect(cell.querySelectorAll('ion-button').length).toBe(1);
    expect(cell.querySelector('[data-testid="dashboard-blueprint-cta"]')).not.toBeNull();
    // No quedan restos del flujo antiguo (dos botones: importar + exportar).
    expect(cell.querySelector('[data-testid="dashboard-blueprint-export"]')).toBeNull();
    expect(cell.querySelector('[data-testid="dashboard-blueprint-import"]')).toBeNull();
  });

  it('el CTA invoca onOpen (aterriza en Datos)', () => {
    const cell = document.createElement('div');
    const onOpen = vi.fn();
    buildBlueprintWidget(cell, t, onOpen);
    (cell.querySelector('[data-testid="dashboard-blueprint-cta"]') as HTMLElement).click();
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
