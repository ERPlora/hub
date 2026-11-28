// What the till says when one of its actions fails: the server's refusal as it came; without a connection, the SDK's
// own sentence, which says the connection is missing (a waiter must not think the product or the kitchen is at
// fault); any other failure nobody worded, the till's sentence for that action.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, describe, expect, it } from 'vitest';

import sdkEn from '../../../../../packages/ui/src/sdk/locales/en.json';
import sdkEs from '../../../../../packages/ui/src/sdk/locales/es.json';
import { mountComposable } from '../../__tests__/mount-sale';
import { useWordsOf } from './useWordsOf';

const KEY = 'sale.pos.options.loadFailed';

async function wordsIn(locale: 'en' | 'es') {
  let wordsOf: ReturnType<typeof useWordsOf> | undefined;
  await mountComposable(
    () => {
      wordsOf = useWordsOf();
    },
    { locale },
  );
  return wordsOf!;
}

/** A request that never reached the server, as the API client rejects it: its sentence in the page's language. */
function offline(lang: string): ApiError {
  document.documentElement.lang = lang;
  return new ApiError(0, 'network_error', (lang === 'es' ? sdkEs : sdkEn).sdk.errors.network, undefined, { reason: 'Failed to fetch' });
}

afterEach(() => {
  document.documentElement.lang = '';
});

describe('useWordsOf', () => {
  it('without a connection says so, in the person’s language, never the action’s sentence', async () => {
    const es = await wordsIn('es');
    expect(es(offline('es'), KEY)).toBe('No se pudo conectar con el servidor. Revisa tu conexión y vuelve a intentarlo en unos segundos.');
    const en = await wordsIn('en');
    expect(en(offline('en'), KEY)).toBe('Could not connect to the server. Check your connection and try again in a few seconds.');
  });

  it('a refusal says the server’s words', async () => {
    const wordsOf = await wordsIn('en');
    expect(wordsOf(new ApiError(409, 'sale.product_not_available', 'That product is no longer in the catalogue.'), KEY)).toBe(
      'That product is no longer in the catalogue.',
    );
  });

  it('a failure nobody worded (a proxy’s page, the server’s own breakdown, not an API error) says the action’s sentence', async () => {
    const wordsOf = await wordsIn('es');
    const sentence = 'No se han podido leer los suplementos de este producto. Inténtalo de nuevo.';
    expect(wordsOf(new ApiError(502, 'unexpected_response', 'Unexpected response (HTTP 502)'), KEY)).toBe(sentence);
    expect(wordsOf(new ApiError(500, 'internal_error', 'Internal error'), KEY)).toBe(sentence);
    expect(wordsOf(new TypeError('boom'), KEY)).toBe(sentence);
  });
});
