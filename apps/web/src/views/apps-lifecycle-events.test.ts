// hub#1317 (spin-off of the hub#1311 review): the runtime did not broadcast anything of its own
// when a module was activated, deactivated or uninstalled — unlike install (`module.installed`,
// hub#631). «Mis apps» (this screen) only learned of the change in the TAB that did it (its own
// `toggleModule`/`removeModule` already reload after the HTTP call resolves); another open
// tab/device of the same hub kept showing yesterday's status/list until it reloaded.
//
// Same place this screen already reacts to `module.installed` (`onMounted`, `apps-core.test.ts`
// covers the reload sequence for the tab that acts): it now also listens for `module.activated` /
// `module.deactivated` / `module.uninstalled` and reloads the same way, and unsubscribes all of
// them on unmount (this view mounts/unmounts on every visit to /apps, unlike App.vue).
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('./AppsPage.vue', import.meta.url), 'utf8');

describe('«Mis apps» reacciona a activate/deactivate/uninstall de OTRA pestaña (hub#1317)', () => {
  const mountedStart = source.indexOf('onMounted(() => {');
  const mountedEnd = source.indexOf('\n});', mountedStart);
  const mounted = source.slice(mountedStart, mountedEnd);

  it.each(['module.activated', 'module.deactivated', 'module.uninstalled'])(
    'se suscribe a %s en onMounted',
    (event) => {
      expect(mounted).toContain(`'${event}'`);
    },
  );

  it('cada suscripción nueva recarga instalados/catálogo/nav, no solo pinta un toast', () => {
    for (const event of ['module.activated', 'module.deactivated', 'module.uninstalled']) {
      const idx = mounted.indexOf(`'${event}'`);
      expect(idx, `${event} debe existir en onMounted`).toBeGreaterThan(-1);
      // Hasta la siguiente suscripción (o el final del bloque): la reacción de ESTE evento.
      const nextClientOn = mounted.indexOf('client.on(', idx + 1);
      const reaction = mounted.slice(idx, nextClientOn === -1 ? undefined : nextClientOn);
      expect(reaction, `${event} debe recargar loadInstalled()`).toContain('loadInstalled(');
      expect(reaction, `${event} debe recargar refreshModuleNav()`).toContain('refreshModuleNav(');
    }
  });

  it('desuscribe los tres eventos nuevos en onBeforeUnmount (esta vista sí se desmonta)', () => {
    const unmountStart = source.indexOf('onBeforeUnmount(() => {');
    const unmountEnd = source.indexOf('\n});', unmountStart);
    const unmount = source.slice(unmountStart, unmountEnd);
    expect(unmount).toMatch(/unsubActivated\?\.\(\)/);
    expect(unmount).toMatch(/unsubDeactivated\?\.\(\)/);
    expect(unmount).toMatch(/unsubUninstalled\?\.\(\)/);
  });
});
