// **El lector de la declaración responsable no completa lo que falta** (hub#528).
//
// El bloque `SistemaInformatico` no tiene hijos opcionales: o están los nueve elementos o no hay
// declaración que enseñar. El runtime ya aplica esa regla del lado del fabricante
// (`ProducerFacts::parse` es todo-o-nada porque un solo carácter mal es el error 1100 de la AEAT en
// todos los registros de toda la flota); estos tests clavan que el navegador no la relaje —
// rellenar un hueco aquí haría que el TPV certificara una identidad que las facturas no llevan, que
// es justo lo que el art. 13 sanciona.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DECLARATION_FIELDS,
  fetchResponsibleDeclaration,
} from './responsible-declaration';

const HUB_ID = '6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10';

/** El bloque completo, tal y como lo sirve `GET /api/system/declaration`. */
function block(): Record<string, string> {
  return {
    NombreRazon: 'ERPLORA CLOUD SL',
    NIF: 'B27593136',
    NombreSistemaInformatico: 'ERPlora Hub',
    IdSistemaInformatico: 'EC',
    Version: '2.4.1',
    NumeroInstalacion: HUB_ID,
    TipoUsoPosibleSoloVerifactu: 'S',
    TipoUsoPosibleMultiOT: 'S',
    IndicadorMultiplesOT: 'N',
  };
}

function stubFetch(payload: unknown, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(payload), { status })),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('lectura de la declaración responsable (hub#528)', () => {
  it('devuelve los nueve elementos en el orden del XSD', async () => {
    stubFetch({
      version: '2.4.1',
      numeroInstalacion: HUB_ID,
      declarationUrl: 'https://erplora.com/legal/declaracion-responsable/',
      sistemaInformatico: block(),
    });

    const declaration = await fetchResponsibleDeclaration();

    expect(Object.keys(declaration.sistemaInformatico ?? {})).toEqual([...DECLARATION_FIELDS]);
    expect(declaration.version).toBe('2.4.1');
    expect(declaration.numeroInstalacion).toBe(HUB_ID);
  });

  it.each(DECLARATION_FIELDS)(
    'sin `%s` no hay bloque: un bloque a medias no es media declaración, es una equivocada',
    async (missing) => {
      const partial = block();
      delete partial[missing];
      stubFetch({
        version: '2.4.1',
        numeroInstalacion: HUB_ID,
        declarationUrl: 'https://erplora.com/legal/declaracion-responsable/',
        sistemaInformatico: partial,
      });

      const declaration = await fetchResponsibleDeclaration();

      expect(declaration.sistemaInformatico, `falta \`${missing}\` y aun así se sirvió`).toBeNull();
      // Lo que este hub sabe de sí mismo no depende del fabricante y se sigue pudiendo enseñar.
      expect(declaration.version).toBe('2.4.1');
      expect(declaration.numeroInstalacion).toBe(HUB_ID);
    },
  );

  it('una negativa del runtime LANZA — nunca resuelve en una declaración vacía', async () => {
    stubFetch({ ok: false }, 401);

    await expect(fetchResponsibleDeclaration()).rejects.toThrow('401');
  });

  it('una respuesta ilegible LANZA en vez de inventarse una URL de archivo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('no soy json', { status: 200 })),
    );

    await expect(fetchResponsibleDeclaration()).rejects.toThrow();
  });
});
