import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const loader = readFileSync(new URL('./module-loader.ts', import.meta.url), 'utf8');
const host = readFileSync(new URL('../views/ModuleView.vue', import.meta.url), 'utf8');

describe('module host', () => {
  it('authenticates internal navigation requests', () => {
    expect(loader).toContain("import { RUNTIME_URL, runtimeHeaders } from './runtime'");
    expect(loader).toContain('headers: runtimeHeaders()');
  });

  it('ignores stale async mounts during rapid internal navigation', () => {
    expect(host).toContain('const generation = ++mountGeneration');
    expect(host).toContain('generation !== mountGeneration');
    expect(host).toContain('onBeforeUnmount');
  });

  it('recovers from a failed module load and canonicalizes retired tabs', () => {
    expect(host).toContain('@click="mount"');
    expect(host).toContain('router.replace(`/m/${moduleId}/${entry.nav.id}`)');
  });

  // ADR-0048 — el canal de chrome está probado de verdad en `immersive.test.ts` (comportamiento).
  // Lo que NO cubre aquel fichero es que ESTA vista lo enchufe: una lib impecable que nadie llama
  // deja el ⋮ del TPV sin nadie al otro lado, y ningún test lo notaría. Aquí se fija el cableado.
  it('wires the module chrome channel and hands the chrome back on the way out', () => {
    expect(host).toContain("from '../lib/immersive'");
    // La concesión sale del manifest CRUDO por pestaña, que es la autoridad de ADR-0048.
    expect(host).toContain('chromeControlsFor(manifest, entry.nav.id)');
    expect(host).toContain('installChrome(outlet.value, chromeControls)');
    // Y se suelta al desmontar: irse del módulo con el chrome escondido deja la pantalla siguiente
    // sin menú y sin el botón del TPV, que era lo único que sabía devolverlo.
    expect(host).toContain('stopChrome?.()');
  });

  it('preserves complete module labels and scrolls before shrinking mobile tabs', () => {
    expect(host).toContain('class="ok-tabbar module-tabbar"');
    expect(host).toContain('scrollable');
    expect(host).toContain(':aria-label="tb.label"');
    expect(host).toContain('--ok-tabbar-min: 116px');
    expect(host).toContain('white-space: normal');
  });
});
