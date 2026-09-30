// hub#1570 — a module's DOMAIN refusal is told in the user's language, using the module's own words.
//
// The incident: with the hub in Spanish, Impuestos → Reglas fiscales refused to bring a rule back
// and the screen showed «That rule could not be brought back: it does not exist in this business,
// or it is already active.» — English, on a Spanish till. The Spanish sentence EXISTED all along:
// `taxes/locales/es.json → errors["taxes.rule_not_deactivated"]`, which ADR-0398 makes the place
// the text lives (the manifest declares that the code EXISTS; `locales/<lang>.json` says what it
// SAYS) and which `erplora validate` already forces to carry both `en` and `es` (ADR-0055).
//
// The SDK never read it. 21 modules ship 197 of these sentences (2026-09-05) and the SDK handed
// the screen the server's `message` verbatim; ten modules had written their own by-code lookup to
// cope, every other screen does the ordinary `this.error = e.message`. Fixing it in a screen fixes
// it once and misses the rest, so it belongs here — the same reasoning as the PLATFORM half
// (hub#1102), one layer down.
//
// Two rules that hold from hub#1102 and are re-asserted below: a PLATFORM code still wins (its
// sentence is written for a person who has no module to blame), and a code nobody translated keeps
// the sentence that arrived — a refusal we cannot say better is one we do not touch.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ErploraClient, ErploraError, HttpWsTransport } from './index.ts';

/** `taxes/locales/*.json` as the Web Component imports them: the whole file, both languages. */
const TAXES_CATALOG: Record<string, unknown> = {
  en: {
    ui: { errRestoreRule: 'The rule could not be restored.' },
    errors: {
      'taxes.rule_not_deactivated':
        'That rule could not be brought back: it does not exist in this business, or it is already active.',
    },
  },
  es: {
    ui: { errRestoreRule: 'No se ha podido recuperar la regla.' },
    errors: {
      'taxes.rule_not_deactivated':
        'No se ha podido recuperar la regla: no existe en este negocio, o ya está activa.',
    },
  },
};

/** What the runtime answers for a module's domain refusal (ADR-0205): 409 + code + prose. */
const SERVER_ENGLISH =
  'That rule could not be brought back: it does not exist in this business, or it is already active.';

function refusing(error: Record<string, unknown>, status = 409): typeof fetch {
  return (async () => ({
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error }),
  })) as unknown as typeof fetch;
}

function clientRefusing(error: Record<string, unknown>): ErploraClient {
  return new ErploraClient(new HttpWsTransport({ baseUrl: 'http://h', fetchImpl: refusing(error) }));
}

/** Runs `body` with the shell's active language set to `lang`, restoring whatever was there. */
async function inLocale(lang: string, body: () => Promise<void>): Promise<void> {
  const g = globalThis as { localStorage?: unknown };
  const prev = g.localStorage;
  g.localStorage = { getItem: (k: string) => (k === 'erplora.locale' ? lang : null) };
  try {
    await body();
  } finally {
    if (prev === undefined) delete g.localStorage;
    else g.localStorage = prev;
  }
}

test('hub#1570: a Spanish hub reads the module\'s Spanish refusal, not the server\'s English one', async () => {
  await inLocale('es', async () => {
    const client = clientRefusing({ code: 'taxes.rule_not_deactivated', message: SERVER_ENGLISH });
    // The screen renders first — this is the very call every module WC already makes for its
    // labels (`erplora().t(CATALOG, 'ui.…')`), and it is what hands the SDK the module's words.
    client.t(TAXES_CATALOG, 'ui.errRestoreRule');

    await assert.rejects(
      () => client.command('taxes.rules.activate', { rule_id: '7' }),
      (e: unknown) => {
        assert.ok(e instanceof ErploraError);
        assert.equal(e.code, 'taxes.rule_not_deactivated', 'the code is the contract: untouched');
        assert.equal(
          e.message,
          'No se ha podido recuperar la regla: no existe en este negocio, o ya está activa.',
        );
        assert.doesNotMatch(
          e.message,
          /could not be brought back/,
          'the English source must not reach a Spanish till',
        );
        return true;
      },
    );
  });
});

test('hub#1570: an English hub reads the English source (ADR-0055), not the Spanish translation', async () => {
  await inLocale('en', async () => {
    // The server sentence is deliberately NOT the catalogue's English one: otherwise this test
    // would pass on a SDK that resolves nothing and just echoes the wire, which is the bug.
    const client = clientRefusing({
      code: 'taxes.rule_not_deactivated',
      message: 'rule 7 is not deactivated (taxes_rules.is_active = 1)',
    });
    client.t(TAXES_CATALOG, 'ui.errRestoreRule');

    await assert.rejects(
      () => client.command('taxes.rules.activate', { rule_id: '7' }),
      (e: unknown) => {
        assert.ok(e instanceof ErploraError);
        assert.match(e.message, /could not be brought back/, 'the module\'s own English sentence');
        assert.doesNotMatch(e.message, /is_active/, 'no column names in front of a person');
        assert.doesNotMatch(e.message, /No se ha podido/, 'en is the source, not the translation');
        return true;
      },
    );
  });
});

test('hub#1570: a language the module never translated falls back to the English source', async () => {
  await inLocale('fr', async () => {
    const client = clientRefusing({ code: 'taxes.rule_not_deactivated', message: 'raw server prose' });
    client.t(TAXES_CATALOG, 'ui.errRestoreRule');

    await assert.rejects(
      () => client.command('taxes.rules.activate', {}),
      (e: unknown) =>
        e instanceof ErploraError && /could not be brought back/.test(e.message),
    );
  });
});

test('hub#1570: a code the module never translated keeps the sentence that arrived (hub#1102 rule 2)', async () => {
  await inLocale('es', async () => {
    const client = clientRefusing({
      code: 'taxes.rule_incoherent',
      message: 'the server sentence for a code with no translation',
    });
    client.t(TAXES_CATALOG, 'ui.errRestoreRule');

    await assert.rejects(
      () => client.command('taxes.rules.create', {}),
      (e: unknown) =>
        e instanceof ErploraError &&
        e.message === 'the server sentence for a code with no translation',
    );
  });
});

test('hub#1570: a PLATFORM failure still wins — its sentence is not a module\'s to override', async () => {
  await inLocale('es', async () => {
    const client = clientRefusing({
      code: 'module_not_installed',
      module: 'taxes',
      message: 'module `taxes` is not installed',
    });
    client.t(TAXES_CATALOG, 'ui.errRestoreRule');

    await assert.rejects(
      () => client.command('sales.complete_sale', {}),
      (e: unknown) => {
        assert.ok(e instanceof ErploraError);
        assert.match(e.message, /Apps/, 'the platform sentence names WHERE to go (hub#1102)');
        return true;
      },
    );
  });
});

test('hub#1570: one module\'s catalogue never answers for another module\'s code', async () => {
  await inLocale('es', async () => {
    const client = clientRefusing({
      code: 'sales.till_closed',
      message: 'the till is closed',
    });
    client.t(TAXES_CATALOG, 'ui.errRestoreRule');

    await assert.rejects(
      () => client.command('sales.complete_sale', {}),
      (e: unknown) => e instanceof ErploraError && e.message === 'the till is closed',
    );
  });
});

test('hub#1570: `{message}` splices the server detail into the module\'s sentence (combos)', async () => {
  // `combos/locales/*.json` writes its one refusal as «… cannot be withdrawn: {message}» in BOTH
  // languages: the module wants its own sentence AND the detail the server computed. Dropping the
  // placeholder on the floor would print a literal `{message}` on the till.
  const combos: Record<string, unknown> = {
    en: { errors: { 'combos.combo_in_use': 'This menu is being used and cannot be withdrawn: {message}' } },
    es: { errors: { 'combos.combo_in_use': 'Este menú se está usando y no se puede retirar: {message}' } },
  };
  await inLocale('es', async () => {
    const client = clientRefusing({ code: 'combos.combo_in_use', message: 'Menú del día' });
    client.t(combos, 'errors.x');

    await assert.rejects(
      () => client.command('combos.withdraw', {}),
      (e: unknown) => {
        assert.ok(e instanceof ErploraError);
        assert.equal(e.message, 'Este menú se está usando y no se puede retirar: Menú del día');
        return true;
      },
    );
  });
});

test('hub#1570: a catalogue with no `errors` block changes nothing and breaks nothing', async () => {
  await inLocale('es', async () => {
    const client = clientRefusing({ code: 'staff.shift_locked', message: 'the shift is locked' });
    client.t({ es: { ui: { title: 'Personal' } } }, 'ui.title');

    await assert.rejects(
      () => client.command('staff.close_shift', {}),
      (e: unknown) => e instanceof ErploraError && e.message === 'the shift is locked',
    );
  });
});

test('hub#1570: a module cannot rewrite a CORE refusal by declaring its bare code', async () => {
  // `not_found`, `conflict`, `permission_denied` are the core's, not a module's (ADR-0052), and so
  // are the three-segment namespaces `hub.*` / `flow.*`. A catalogue with a stray key like these is
  // ignored on the way IN: whatever a module wrote about someone else's refusal never gets spoken.
  const rogue: Record<string, unknown> = {
    es: {
      errors: {
        not_found: 'Lo que buscas no existe (según un módulo cualquiera)',
        'hub.fiscal.duplicate': 'Un módulo opinando sobre el registro fiscal del núcleo',
      },
    },
  };
  await inLocale('es', async () => {
    const client = clientRefusing({ code: 'not_found', message: 'the core sentence' });
    client.t(rogue, 'errors.not_found');

    await assert.rejects(
      () => client.command('hub.staff.update', {}),
      (e: unknown) => e instanceof ErploraError && e.message === 'the core sentence',
    );
  });

  await inLocale('es', async () => {
    const client = clientRefusing({ code: 'hub.fiscal.duplicate', message: 'the fiscal sentence' });
    client.t(rogue, 'errors.not_found');

    await assert.rejects(
      () => client.command('hub.fiscal.emit', {}),
      (e: unknown) => e instanceof ErploraError && e.message === 'the fiscal sentence',
    );
  });
});

test('hub#1570: an empty translation is no translation — the server sentence survives', async () => {
  const blank: Record<string, unknown> = { es: { errors: { 'staff.shift_locked': '' } } };
  await inLocale('es', async () => {
    const client = clientRefusing({ code: 'staff.shift_locked', message: 'the shift is locked' });
    client.t(blank, 'errors.x');

    await assert.rejects(
      () => client.command('staff.close_shift', {}),
      (e: unknown) => e instanceof ErploraError && e.message === 'the shift is locked',
    );
  });
});

test('hub#1570: no PLATFORM code is domain-shaped — which is WHY a module can never shadow one', async () => {
  // The order inside `unwrap` (platform first, module second) is only ever visible if one code
  // could be both. It cannot: every code the SDK answers for as PLATFORM is a bare word, and only
  // `<module>.<snake_case>` is ever indexed as a module refusal. That disjointness is the real
  // guard, so it is pinned here rather than left as a coincidence for the next change to break.
  const { platformFailureMessage } = await import('./index.ts');
  const domainShaped = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;
  const platformCodes = [
    'read_unavailable',
    'module_not_installed',
    'missing_dependency',
    'module_inactive',
    'db',
    'io',
    'wasm',
    'wasm_budget_exceeded',
    'wasm_timeout',
    'native',
    'schema',
    'manifest',
    'error',
  ];
  for (const code of platformCodes) {
    assert.ok(
      platformFailureMessage({ code, module: 'taxes' }, 'es'),
      `"${code}" no longer has a PLATFORM sentence — this list drifted from PLATFORM_FAILURES`,
    );
    assert.doesNotMatch(
      code,
      domainShaped,
      `"${code}" is shaped like a module code: a module catalogue could now shadow a platform ` +
        'failure, and the sentence written for someone with no app to blame would be lost',
    );
  }
});

test('hub#1570: a CORE namespace with two segments (`flow.*`, `hub.*`, `fiscal.*`) is never a module\'s to rewrite', async () => {
  // `flow.grant_denied`, `hub.migration_lock_timeout` and `fiscal.hub_closed` are codes the core
  // itself emits (`crates/runtime/src/flows`, `dispatch.rs`, `fiscal_profile.rs`). They are shaped
  // exactly like a module code — two snake segments — so the SHAPE guard alone would let a stray
  // catalogue key answer for them. The core's namespaces are refused by NAME on the way in: no
  // module is called `hub`, `flow` or `fiscal`, and none gets to speak for the core (§8.5).
  const rogue: Record<string, unknown> = {
    es: {
      errors: {
        'flow.grant_denied': 'Un módulo opinando sobre el permiso de un flujo',
        'hub.migration_lock_timeout': 'Un módulo opinando sobre la migración del núcleo',
        'fiscal.hub_closed': 'Un módulo opinando sobre el cierre fiscal',
      },
    },
  };
  const cases: Array<[string, string]> = [
    ['flow.grant_denied', 'the flow sentence'],
    ['hub.migration_lock_timeout', 'the migration sentence'],
    ['fiscal.hub_closed', 'the fiscal sentence'],
  ];
  for (const [code, message] of cases) {
    await inLocale('es', async () => {
      const client = clientRefusing({ code, message });
      client.t(rogue, 'errors.x');

      await assert.rejects(
        () => client.command('hub.flows.run', {}),
        (e: unknown) => {
          assert.ok(e instanceof ErploraError);
          assert.equal(e.message, message, `${code}: the core's own sentence must survive a rogue catalogue`);
          return true;
        },
      );
    });
  }
});

test('hub#1570: a catalogue that carries the code in `es` only, on a hub in another language, keeps the server sentence', async () => {
  // `erplora validate` forces `en` + `es`, so this catalogue is hand-made — the chain still has to
  // hold: `locale → en → nothing`, and «nothing» is the sentence that arrived, never a crash.
  const esOnly: Record<string, unknown> = {
    es: { errors: { 'tables.table_occupied': 'Esa mesa está ocupada.' } },
  };
  await inLocale('fr', async () => {
    const client = clientRefusing({ code: 'tables.table_occupied', message: 'table 4 is occupied' });
    client.t(esOnly, 'errors.x');

    await assert.rejects(
      () => client.command('tables.seat', {}),
      (e: unknown) => e instanceof ErploraError && e.message === 'table 4 is occupied',
    );
  });
});
