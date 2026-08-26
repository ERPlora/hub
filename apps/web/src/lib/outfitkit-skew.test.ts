// El aviso de DERIVA de OutfitKit entre el shell y un módulo (hub#1024).
//
// Un módulo publicado hornea SU copia de OutfitKit (`erplora build` la resuelve desde los
// node_modules del toolkit: el checkout local de quien construyó). En un hub real esa copia casi
// nunca manda — el shell define sus `ok-*` al arrancar y el `define()` horneado está guardado
// (`if (!customElements.get(tag))`), así que pierde en silencio— mientras la imagen instala
// `@erplora/outfitkit@latest` en CADA build.
//
// O sea: la página corre DOS OutfitKit repartidos elemento por elemento, y hasta hoy nadie comparaba
// esas dos versiones. Un cambio de contrato rompía módulos publicados sin que ningún test lo viera,
// y en `pnpm dev` no reproducía porque ahí las dos copias son el mismo checkout — que es justo lo
// que llevó a cerrar hub#754/#804 con un «no reproducible en develop».
//
// Esto NO arregla la deriva. La hace visible: una línea en consola, nombrando el módulo y las dos
// versiones. Lo que no se puede ver, no se puede arreglar.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { warnOnOutfitkitSkew, resetOutfitkitSkewWarnings } from './outfitkit-skew';

beforeEach(() => {
  resetOutfitkitSkewWarnings();
  vi.restoreAllMocks();
});

describe('cuando las versiones difieren', () => {
  it('avisa una vez, nombrando el módulo y las DOS versiones', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    warnOnOutfitkitSkew('appointments', '0.1.31', '0.1.40');

    expect(warn).toHaveBeenCalledTimes(1);
    const said = String(warn.mock.calls[0]?.join(' '));
    expect(said).toContain('appointments');
    expect(said).toContain('0.1.31');
    expect(said).toContain('0.1.40');
  });

  it('no repite por cada pestaña del mismo módulo', () => {
    // El shell carga el bundle de un módulo varias veces por sesión (menú, widgets, slots). Un
    // aviso por carga convierte la consola en ruido y el ruido se ignora — que es como no avisar.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    warnOnOutfitkitSkew('appointments', '0.1.31', '0.1.40');
    warnOnOutfitkitSkew('appointments', '0.1.31', '0.1.40');
    warnOnOutfitkitSkew('appointments', '0.1.31', '0.1.40');

    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('pero sí avisa de OTRO módulo con la misma deriva', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    warnOnOutfitkitSkew('appointments', '0.1.31', '0.1.40');
    warnOnOutfitkitSkew('sales', '0.1.31', '0.1.40');

    expect(warn).toHaveBeenCalledTimes(2);
  });
});

describe('cuando NO hay nada que decir, se calla', () => {
  it('con la misma versión', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    warnOnOutfitkitSkew('appointments', '0.1.40', '0.1.40');
    expect(warn).not.toHaveBeenCalled();
  });

  it('sin sello del módulo — son los 25 publicados de hoy, no un defecto suyo', () => {
    // Avisar de todos ellos en cada arranque enterraría el aviso que sí importa.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    warnOnOutfitkitSkew('appointments', undefined, '0.1.40');
    expect(warn).not.toHaveBeenCalled();
  });

  it('sin versión del shell — no se compara contra un hueco', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    warnOnOutfitkitSkew('appointments', '0.1.31', '');
    expect(warn).not.toHaveBeenCalled();
  });
});
