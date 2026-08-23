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

  // ── hub#1099 — la vista que Ionic deja ATRÁS sigue viva, y seguía trabajando ──────────────────
  //
  // Ionic NO desmonta la página que dejas cuando entras a otra con un `push` en dirección
  // `forward`, y las TRES puertas a un módulo lo son (launcher de la topbar, tarjeta «Mis apps»,
  // botón Abrir de /apps). La vista se queda montada, solo escondida: `onBeforeUnmount` NO llega a
  // ejecutarse por ese camino. Así que cada navegación dejaba una copia más de esta vista, con su
  // watcher de ruta, y CADA copia volvía a correr `mount()` entero —los 25 manifests, la
  // navegación y el guard— en la siguiente navegación. De ahí que el coste creciera con cada
  // navegación y no volviera a bajar nunca con el hub en reposo.
  it('no vuelve a montarse mientras está fuera de pantalla (hub#1099)', () => {
    expect(host).toContain('onIonViewDidLeave');
    expect(host).toContain('onIonViewWillEnter');
    // El watcher de ruta es quien multiplicaba: tiene que rendirse si esta copia no es la visible.
    const idx = host.indexOf('watch(\n  () => [route.params.moduleId, route.params.navId]');
    expect(idx).toBeGreaterThan(-1);
    expect(host.slice(idx, idx + 600)).toContain('onScreen');
  });

  it('suelta lo que tenía enganchado al irse de pantalla, no solo al desmontarse (hub#1099)', () => {
    // El listener de `focus` y el canal de chrome se soltaban SOLO en `onBeforeUnmount`, que por lo
    // de arriba no llega: tras 8 navegaciones, un solo foco de ventana disparaba 8 consultas de
    // entitlement al Cloud, y quedaban 8 MutationObserver mirando outlets escondidos.
    const idx = host.indexOf('onIonViewDidLeave(() => {');
    const after = host.slice(idx, idx + 700);
    expect(after).toContain("removeEventListener('focus'");
    expect(after).toContain('stopChrome');
    expect(after).toContain('clearProtectsSubscription()');
  });

  it('preserves complete module labels and scrolls before shrinking mobile tabs', () => {
    expect(host).toContain('class="ok-tabbar module-tabbar"');
    expect(host).toContain('scrollable');
    expect(host).toContain(':aria-label="tb.label"');
    expect(host).toContain('--ok-tabbar-min: 116px');
    expect(host).toContain('white-space: normal');
  });
});
