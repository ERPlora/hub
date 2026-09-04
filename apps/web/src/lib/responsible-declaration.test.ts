// **The responsible declaration reader does not fill in what is missing** (hub#528).
//
// The `SistemaInformatico` block has no optional children: either the nine elements are there or
// there is no declaration to show. The runtime already applies that rule on the manufacturer's
// side (`ProducerFacts::parse` is all-or-nothing because a single wrong character is AEAT error
// 1100 on every record of the whole fleet); these tests pin that the browser does not relax it —
// filling a gap here would make the till certify an identity the invoices do not carry, which is
// exactly what art. 13 sanctions.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DECLARATION_FIELDS,
  fetchResponsibleDeclaration,
} from './responsible-declaration';

const HUB_ID = '6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10';

/** The complete block, exactly as `GET /api/system/declaration` serves it. */
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

describe('reading the responsible declaration (hub#528)', () => {
  it('returns the nine elements in XSD order (hub#528)', async () => {
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
    'without `%s` there is no block: a partial block is not half a declaration, it is a wrong one (hub#528)',
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

      expect(declaration.sistemaInformatico, `\`${missing}\` is missing and the block was served anyway`).toBeNull();
      // What this hub knows about itself does not depend on the manufacturer and can still be shown.
      expect(declaration.version).toBe('2.4.1');
      expect(declaration.numeroInstalacion).toBe(HUB_ID);
    },
  );

  it('carries the version of the declaration the control plane named (hub#1510)', async () => {
    stubFetch({
      version: '2.4.1',
      numeroInstalacion: HUB_ID,
      declarationUrl: 'https://erplora.com/legal/declaracion-responsable/v2/',
      declarationVersion: 'v2',
      sistemaInformatico: block(),
    });

    const declaration = await fetchResponsibleDeclaration();

    expect(declaration.declarationVersion).toBe('v2');
    // A different fact from the BINARY's version: the release this hub runs, not the text
    // covering it. Conflating them is what hub#1510 exists to avoid.
    expect(declaration.version).toBe('2.4.1');
  });

  it.each([undefined, null, '', '   '])(
    'with %o as the declaration version there is NO version, not an empty label (hub#1510)',
    async (served) => {
      stubFetch({
        version: '2.4.1',
        numeroInstalacion: HUB_ID,
        declarationUrl: 'https://erplora.com/legal/declaracion-responsable/',
        declarationVersion: served,
        sistemaInformatico: block(),
      });

      const declaration = await fetchResponsibleDeclaration();

      expect(declaration.declarationVersion).toBeUndefined();
      // The link keeps resolving: the archive-root fallback of hub#528 is untouched.
      expect(declaration.declarationUrl).toBe('https://erplora.com/legal/declaracion-responsable/');
    },
  );

  it('a runtime refusal THROWS — it never resolves into an empty declaration (hub#528)', async () => {
    stubFetch({ ok: false }, 401);

    await expect(fetchResponsibleDeclaration()).rejects.toThrow('401');
  });

  it('an unreadable response THROWS instead of inventing an archive URL (hub#528)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('no soy json', { status: 200 })),
    );

    await expect(fetchResponsibleDeclaration()).rejects.toThrow();
  });
});
