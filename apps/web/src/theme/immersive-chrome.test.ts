// @vitest-environment happy-dom
// El modo inmersivo, del lado del CSS: `html.immersive` tiene que ESCONDER de verdad el chrome.
//
// `lib/immersive.ts` solo pone la clase; quien hace el trabajo son estas reglas. Separarlas dejaba
// media función sin prueba: un selector que no case (un `>` de más, una clase renombrada) deja el
// modo activado y el menú en su sitio, y el test de la marca en el documento seguiría verde.
//
// Por eso esto NO es una comprobación de texto sobre el CSS: se monta el árbol REAL del shell
// (`ion-app > ion-split-pane > ion-menu` + `ion-router-outlet#main > .ion-page > header/content/
// footer`), se le carga `polish.css` y se pregunta al motor de estilos. Si mañana alguien cambia la
// estructura de `App.vue` o de `AppPage.vue`, este test cae — que es justo lo que se le pide.
import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Ruta desde el cwd (apps/web) y no desde `import.meta.url`: bajo happy-dom la URL del módulo no
// es `file:` y `readFileSync` la rechaza.
const polish = readFileSync(join(process.cwd(), 'src/theme/polish.css'), 'utf8');

/** Monta el esqueleto del shell tal y como lo pintan App.vue + AppPage.vue + ModuleView.vue. */
function montarShell(): Record<string, HTMLElement> {
  document.head.innerHTML = '';
  document.body.innerHTML = '';
  document.documentElement.className = '';

  const style = document.createElement('style');
  style.textContent = polish;
  document.head.appendChild(style);

  document.body.innerHTML = `
    <ion-app>
      <ion-split-pane content-id="main">
        <ion-menu class="dash-menu"><ion-content class="sidebar-content"></ion-content></ion-menu>
        <ion-router-outlet id="main" class="split-pane-main">
          <div class="ion-page">
            <ion-header class="app-topbar"><ion-toolbar></ion-toolbar></ion-header>
            <ion-content></ion-content>
            <ion-footer><ion-toolbar><ion-segment class="module-tabbar"></ion-segment></ion-toolbar></ion-footer>
          </div>
        </ion-router-outlet>
      </ion-split-pane>
    </ion-app>`;

  const pick = (sel: string): HTMLElement => document.querySelector<HTMLElement>(sel)!;
  return {
    menu: pick('ion-menu.dash-menu'),
    topbar: pick('ion-header.app-topbar'),
    tabbar: pick('ion-footer'),
    content: pick('ion-router-outlet#main > .ion-page > ion-content'),
  };
}

const visible = (el: HTMLElement): boolean => getComputedStyle(el).display !== 'none';

describe('CSS del modo inmersivo', () => {
  let shell: Record<string, HTMLElement>;

  beforeEach(() => {
    shell = montarShell();
  });

  it('CONTROL: sin la marca, el chrome del shell está a la vista', () => {
    // Si esto no fuese verdad, los asertos de abajo pasarían sin probar nada (un selector que no
    // case daría «oculto» en los dos estados y el test seguiría verde).
    expect(visible(shell.menu)).toBe(true);
    expect(visible(shell.topbar)).toBe(true);
    expect(visible(shell.tabbar)).toBe(true);
  });

  it('con la marca esconde la barra lateral, la topbar y el tabbar del módulo', () => {
    document.documentElement.classList.add('immersive');

    expect(visible(shell.menu)).toBe(false);
    expect(visible(shell.topbar)).toBe(false);
    expect(visible(shell.tabbar)).toBe(false);
  });

  it('deja la pantalla de venta a sangre: sin tarjeta redondeada ni margen', () => {
    // La tarjeta redondeada del shell (radio 25px + 16px de padding) es chrome también: en modo
    // inmersivo se retira para que la rejilla de productos se quede con todo el lienzo.
    document.documentElement.classList.add('immersive');
    const estilo = getComputedStyle(shell.content);

    expect(estilo.borderRadius).toBe('0px');
    expect(estilo.getPropertyValue('--padding-top').trim()).toBe('0px');
  });
});
