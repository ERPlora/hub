// Guard del REGISTRO ÚNICO de iconos (Iconify horneado en build).
//
// Por qué existe: `ion-icon` resuelve `name="x"` contra el mapa global `window.Ionicons.map`
// (ionicons/dist/collection/components/icon/utils.js) y, si el nombre no está, intenta BAJAR el
// SVG por red → offline/CSP falla y el icono se queda VACÍO, sin error. El fallo es invisible.
//
// Este test convierte ese silencio en rojo: escanea todos los `<ion-icon name="…">` que se
// ejecutan de verdad —shell, OutfitKit (ok-*) y los Web Components de los módulos— y exige que
// cada nombre esté en el registro de `lib/icons.ts`, la ÚNICA fuente de verdad (que alimenta
// tanto `resolveIcon()` para la prop `icon=` como `addIcons()` para el atributo `name=`).
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { moduleIconRegistry, resolveIcon } from './icons';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/**
 * Cada uno pinta sus iconos, y cada uno los TRAE de un sitio distinto. El guard verifica a cada
 * cual contra SU dueño, no todos contra el shell:
 *
 *   · shell     → lib/icons.ts (este registro). Incluye los nombres que el shell le PASA por prop
 *                 a un ok-* (`<ok-kpi icon="receipt-outline">`), que acaban en un ion-icon.
 *   · OutfitKit → los hornea en su propio bundle (base/icons.ts) y los pinta con `.icon`. Ya no
 *                 depende del host, así que no tiene nada que exigirle a este registro.
 *   · módulos   → su sidecar `dist/icons.json` (module-toolkit build). Un módulo de TERCEROS no
 *                 puede depender de que alguien añada su icono aquí a mano.
 */
const SHELL = { label: 'shell', dir: join(WEB, 'src'), exts: ['.ts', '.vue'] };
const MODULES_DIR = join(WEB, 'public', 'modules');

function walk(dir: string, exts: string[], out: string[] = []): string[] {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, exts, out);
    // Los tests quedan fuera: este fichero lleva markup de ejemplo en los comentarios y el
    // escaneo se leería a sí mismo.
    else if (exts.includes(extname(entry.name)) && !entry.name.endsWith('.test.ts')) out.push(path);
  }
  return out;
}

// Un nombre de icono válido para ionicons: solo minúsculas, dígitos y guion (getName() descarta
// cualquier otra cosa — por eso el prefijo de colección de Iconify, `mdi:home`, NO vale en `name=`).
const ICON_NAME = /^[a-z][a-z0-9-]*$/;

/**
 * Nombres de icono escritos de forma estática en un fichero:
 *   <ion-icon name="cart-outline">            → cart-outline
 *   <ion-icon name=${open ? 'x' : 'y'}>       → x, y   (los literales del ternario)
 *   <ok-kpi icon="receipt-outline">           → receipt-outline  (la prop acaba en un ion-icon)
 *   <HubIcon name="save-outline">             → save-outline
 * Los nombres que solo existen en runtime (`name=${this.icon}`) no son verificables aquí; los
 * cubre el fallback de `resolveIcon`.
 */
function iconNamesIn(source: string): string[] {
  const names: string[] = [];
  const tags = source.match(/<(?:ion-icon|HubIcon|ok-[a-z-]+)\b[^>]*>/g) ?? [];
  for (const tag of tags) {
    // En un ion-icon/HubIcon el icono va en `name=` (o `icon=`). En un ok-* solo `icon=` acaba
    // pintando un ion-icon: su `name=` es otra cosa (el id de una pestaña, de un campo…).
    const attr = /^<(?:ion-icon|HubIcon)\b/.test(tag) ? '(?:name|icon)' : 'icon';

    // Atributo estático — `name="cart-outline"`: el valor ES el nombre del icono.
    for (const m of tag.matchAll(new RegExp(`(?<![:.\\w-])${attr}="([a-z][a-z0-9-]*)"`, 'g'))) {
      names.push(m[1]);
    }
    // Enlazado en Lit — `name=${open ? 'a' : 'b'}`: solo los literales de la expresión (los
    // identificadores, `name=${this.icon}`, no son verificables aquí). Los módulos se escanean ya
    // compilados, y esbuild normaliza las comillas a dobles → hay que aceptar ambas.
    for (const m of tag.matchAll(new RegExp(`${attr}=\\$\\{[^}]*\\}`, 'g'))) {
      for (const quoted of m[0].match(/['"][a-z][a-z0-9-]*['"]/g) ?? []) names.push(quoted.slice(1, -1));
    }
    // Enlazado en Vue — `:icon="icon"` es una expresión: solo cuenta un literal ANIDADO en
    // comillas simples (`:icon="'save-outline'"`), nunca el identificador.
    for (const m of tag.matchAll(new RegExp(`[:.]${attr}="[^"]*"`, 'g'))) {
      for (const quoted of m[0].match(/'[a-z][a-z0-9-]*'/g) ?? []) names.push(quoted.slice(1, -1));
    }
  }
  return names.filter((name) => ICON_NAME.test(name));
}

/** El registro devuelve el icono de fallback (`cube-outline`) para todo nombre que NO conoce. */
const FALLBACK = resolveIcon('__nombre-que-no-existe__');
const FALLBACK_NAME = 'cube-outline';

describe('registro único de iconos', () => {
  it('todo icono que pinta el SHELL está en el registro', () => {
    const used = new Set<string>();
    for (const file of walk(SHELL.dir, SHELL.exts)) {
      for (const name of iconNamesIn(readFileSync(file, 'utf8'))) used.add(name);
    }

    // Si el escaneo no encuentra nada, el guard sería verde por vacío: eso también es un fallo.
    expect(used.size, 'el escaneo no encontró ningún ion-icon — el guard no está mirando nada').toBeGreaterThan(10);

    const missing = [...used]
      .filter((name) => name !== FALLBACK_NAME && resolveIcon(name) === FALLBACK)
      .sort();

    expect(missing, 'iconos del shell que NO están en el registro → se pintan VACÍOS').toEqual([]);
  });

  it('los módulos instalados traen su sidecar de iconos (no dependen de este registro)', () => {
    // Que el sidecar de cada módulo esté COMPLETO se verifica donde se ve el fuente del módulo:
    // en `module-toolkit` (test/icons.test.mjs), que es quien lo hornea. Aquí no se puede: el
    // bundle del módulo lleva OutfitKit EMBEBIDO dentro, así que sus iconos y los de la librería
    // son indistinguibles en el .js compilado.
    //
    // Lo que sí se comprueba aquí es el contrato de entrega: el módulo LLEGA con su icons.json, que
    // es lo que el module-loader registra (addIcons) al cargarlo. Sin él, sus <ion-icon name="…">
    // volverían a depender de este registro y saldrían vacíos en el Hub offline.
    if (!existsSync(MODULES_DIR)) return; // sin `sync-modules` no hay módulos que comprobar.

    const sinSidecar: string[] = [];
    let checked = 0;

    for (const moduleId of readdirSync(MODULES_DIR)) {
      const moduleDir = join(MODULES_DIR, moduleId);
      // Solo los módulos que traen un Web Component: uno declarativo puro no pinta iconos.
      if (!walk(moduleDir, ['.js']).length) continue;
      checked++;
      if (!walk(moduleDir, ['.json']).some((f) => f.endsWith('icons.json'))) sinSidecar.push(moduleId);
    }

    expect(checked, 'no se encontró ningún módulo instalado').toBeGreaterThan(0);
    expect(sinSidecar, 'módulos sin dist/icons.json → sus iconos saldrán VACÍOS').toEqual([]);
  });

  it('los iconos que trae un MÓDULO se pueden registrar sin que el shell los conozca', () => {
    // Un módulo (incluso de terceros, instalado desde el marketplace) viaja con su
    // `dist/icons.json` (nombre → SVG inline, horneado por module-toolkit). El shell no puede
    // saber qué iconos usa: los registra tal cual al cargarlo. Esto es lo que hace que un módulo
    // sea AUTÓNOMO y no dependa de que alguien añada su icono a mano a lib/icons.ts.
    const propio = 'un-icono-que-el-shell-no-conoce';
    const registry = moduleIconRegistry({ [propio]: '<svg viewBox="0 0 512 512"><path d="M1 2"/></svg>' });

    const icon = registry[propio];
    expect(icon).toBeDefined();
    // Formato CSP-safe: ionicons lo parsea con DOMParser en vez de hacer fetch (ver iconify.ts).
    expect(icon.startsWith('data:image/svg+xml')).toBe(true);
    expect(icon.includes(';utf8,')).toBe(true);
  });

  it('un módulo NO re-registra un icono que el shell ya tiene (ionicons avisaría de duplicado)', () => {
    // El SVG del shell (unplugin-icons) y el del módulo (@iconify/utils) son el mismo dibujo pero
    // no el mismo string. Registrar ambos con el mismo nombre hace que ionicons escupa
    // "Multiple icons were mapped to name …" en la consola. El primero gana, así que el módulo
    // solo aporta lo que falta.
    const registry = moduleIconRegistry({
      'cart-outline': '<svg viewBox="0 0 512 512"><path d="OTRO DIBUJO"/></svg>', // el shell ya lo trae
      'un-icono-solo-del-modulo': '<svg viewBox="0 0 512 512"><path d="M1 2"/></svg>',
    });

    expect(Object.keys(registry)).toEqual(['un-icono-solo-del-modulo']);
  });

  it('el shell no mantiene un segundo registro de iconos desde ionicons/icons', () => {
    // Dos registros paralelos (lib/icons.ts con Iconify + main.ts con ionicons/icons) se
    // desincronizan: un icono presente en uno y ausente en el otro sale vacío según quién lo pinte.
    // La fuente de verdad es lib/icons.ts; main.ts solo la vuelca con addIcons().
    const main = readFileSync(join(WEB, 'src', 'main.ts'), 'utf8');
    expect(main).not.toMatch(/from '?"?ionicons\/icons'?"?/);
  });
});
