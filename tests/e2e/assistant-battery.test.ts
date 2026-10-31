// @vitest-environment node
// The pure parts of the assistant's QA battery with the real model (qa/assistant-battery.spec.ts): reading the
// streamed turns of `/api/assistant/turn`, the automatic verdict of each item, the report and the seed of the real
// providers on the stack's SaaS. The spec itself only runs with QA_REAL_PROVIDER=1, never in CI.
import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import {
  citationsOf,
  ITEMS,
  languageOf,
  observe,
  type Outcome,
  parseFrames,
  redact,
  renderReport,
  SEED_PY,
  seedCommand,
  verdictOf,
} from './assistant-battery';

const sse = (...frames: object[]): string => frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('');

const DOCS = JSON.stringify({
  results: [
    { source: 'app_doc', path: 'staff/README.md', heading: 'Equipo › Alta', text: '…', score: 0.71, lang: 'es' },
    { source: 'help', path: 'help/pin.md', heading: 'PIN', text: '…', score: 0.6, lang: 'es' },
  ],
});

/** A how-to turn: the model asks for the docs (first response), the Hub runs them and the model answers (second). */
const HOWTO = [
  sse(
    { type: 'text', text: '' },
    { type: 'done', append: [], pending: [{ call_id: 'c1', name: 'base__docs__search', arguments: '{}' }], continuation: 't' },
  ),
  sse(
    { type: 'executed', call_id: 'c1', name: 'base.docs.search', app: 'base', kind: 'query', outcome: 'ok', code: '' },
    { type: 'text', text: 'Ve a Equipo ' },
    { type: 'text', text: 'y pulsa Añadir.' },
    { type: 'usage', used: 4, limit: 30, resets_at: '2026-11-01', demo: false },
    { type: 'done', append: [{ role: 'tool', tool_call_id: 'c1', content: DOCS }], pending: [], continuation: null },
  ),
];

function outcome(id: string, overrides: Partial<Outcome> = {}): Outcome {
  const item = ITEMS.find((each) => each.id === id);
  if (!item) throw new Error(`no item ${id}`);
  return {
    item,
    answer: 'Ve a Equipo y pulsa Añadir.',
    receipts: [],
    notices: [],
    observed: observe(HOWTO),
    decided: 'none',
    screenshot: `/tmp/${id}.png`,
    ...overrides,
  };
}

describe('parseFrames', () => {
  it('reads every data line of the stream as one frame, CRLF or not, and skips comments and blank keep-alives', () => {
    const body = `: ping\r\n\r\ndata: {"type":"text","text":"a"}\r\n\r\ndata: {"type":"done"}\n\n`;
    expect(parseFrames(body)).toEqual([{ type: 'text', text: 'a' }, { type: 'done' }]);
  });

  it('says which line it could not read instead of dropping it', () => {
    expect(() => parseFrames('data: {"type":')).toThrow(/data: \{"type":/);
  });
});

describe('observe', () => {
  it('keeps what ran, the citations of the docs search, the usage and no card for a how-to', () => {
    const seen = observe(HOWTO);
    expect(seen.executed).toEqual([{ name: 'base.docs.search', kind: 'query', outcome: 'ok', code: '' }]);
    expect(seen.citations.map((c) => `${c.source} ${c.path} ${c.heading} ${c.lang}`)).toEqual([
      'app_doc staff/README.md Equipo › Alta es',
      'help help/pin.md PIN es',
    ]);
    expect(seen.usage).toEqual({ used: 4, limit: 30 });
    expect(seen.cards).toEqual([]);
    expect(seen.errors).toEqual([]);
    expect(seen.text).toBe('Ve a Equipo y pulsa Añadir.');
  });

  it('keeps the card of a write and the error a turn ends with', () => {
    const card = { operation: 'customer.customer.create', app: 'customer', risk: 'normal', confirm_word: '', fields: [] };
    const seen = observe([sse({ type: 'confirm', card, call: { call_id: 'w1' } }), sse({ type: 'error', code: 'assistant.cut' })]);
    expect(seen.cards).toEqual([{ operation: 'customer.customer.create', risk: 'normal', confirmWord: '' }]);
    expect(seen.errors).toEqual(['assistant.cut']);
  });

  it('never takes the results of another tool for citations', () => {
    const other = sse(
      { type: 'executed', call_id: 'r1', name: 'customer.customer.list', kind: 'query', outcome: 'ok', code: '' },
      { type: 'done', append: [{ role: 'tool', tool_call_id: 'r1', content: DOCS }], pending: [] },
    );
    expect(observe([other]).citations).toEqual([]);
  });
});

describe('citationsOf', () => {
  it('still reads the excerpts of a result the Hub cut at its size limit', () => {
    const cut = `${DOCS.slice(0, DOCS.indexOf('"text":"…","score":0.6'))} …(cut)`;
    expect(citationsOf(cut).map((c) => c.path)).toEqual(['staff/README.md', 'help/pin.md']);
  });

  it('gives nothing for an error the tool answered', () => {
    expect(citationsOf('{"error":"base.assistant_unavailable"}')).toEqual([]);
  });
});

describe('languageOf', () => {
  it('tells English from Spanish by their common words', () => {
    expect(languageOf('Go to Team and tap Add. Then type the PIN of the employee and save it.')).toBe('en');
    expect(languageOf('Ve a Equipo y pulsa Añadir. Después escribe el PIN del empleado y guárdalo.')).toBe('es');
    expect(languageOf('OK')).toBe('unknown');
  });
});

describe('ITEMS', () => {
  it('holds block B (21 to 34) and C35 to C37, each once, with a slug fit for a file name', () => {
    expect(ITEMS.map((item) => item.id)).toEqual([
      'B21', 'B22', 'B23', 'B24', 'B25', 'B26', 'B27', 'B28', 'B28b', 'B28c', 'B29', 'B30', 'B31', 'B32', 'B33', 'B34', 'C35',
      'C36', 'C37',
    ]);
    for (const item of ITEMS) expect(item.slug).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    expect(ITEMS.filter((item) => item.language === 'en').map((item) => item.id)).toEqual(['C37']);
  });
});

describe('verdictOf', () => {
  it('passes a how-to that searched the docs, cited them and wrote nothing', () => {
    expect(verdictOf(outcome('B21')).verdict).toBe('PASS');
  });

  it('fails a how-to that never searched the docs, naming why', () => {
    const v = verdictOf(outcome('B22', { observed: { ...observe(HOWTO), executed: [], citations: [] } }));
    expect(v.verdict).toBe('FAIL');
    expect(v.reasons.join(' ')).toMatch(/base\.docs\.search did not run/);
  });

  it('fails any item whose turn ended with an error', () => {
    const v = verdictOf(outcome('B21', { observed: { ...observe(HOWTO), errors: ['assistant.provider_failed'] } }));
    expect(v.verdict).toBe('FAIL');
    expect(v.reasons.join(' ')).toMatch(/assistant\.provider_failed/);
  });

  it('fails an answer that wrote nothing but got the «it said it made a change» notice (a how-to, a read)', () => {
    const v = verdictOf(outcome('B25', { notices: ['claimed_change'] }));
    expect(v.verdict).toBe('FAIL');
    expect(v.reasons.join(' ')).toMatch(/claimed a change/);
    const read = { ...observe([]), executed: [{ name: 'sale.sale.today', kind: 'query', outcome: 'ok', code: '' }] };
    expect(verdictOf(outcome('B32', { observed: read, notices: ['claimed_change'] })).verdict).toBe('FAIL');
    expect(verdictOf(outcome('B25', { notices: ['unknown_screen'] })).verdict).toBe('PASS');
  });

  it('fails the SAP trap when a business tool ran, and passes it with only the always-offered ones', () => {
    expect(verdictOf(outcome('B27')).verdict).toBe('PASS');
    const ran = { ...observe(HOWTO), executed: [{ name: 'sale.sale.list', kind: 'query', outcome: 'ok', code: '' }] };
    expect(verdictOf(outcome('B27', { observed: ran })).verdict).toBe('FAIL');
  });

  it('passes a write only with its card confirmed, a command that ran and the record checked through the API', () => {
    const wrote = {
      ...observe([]),
      cards: [{ operation: 'customer.customer.create', risk: 'normal', confirmWord: '' }],
      executed: [{ name: 'customer.customer.create', kind: 'command', outcome: 'ok', code: '' }],
    };
    expect(verdictOf(outcome('B29', { observed: wrote, decided: 'confirmed', record: { checked: 'Ana QA listed', ok: true } })).verdict).toBe('PASS');
    expect(verdictOf(outcome('B29', { observed: wrote, decided: 'confirmed', record: { checked: 'Ana QA listed', ok: false } })).verdict).toBe('FAIL');
    expect(verdictOf(outcome('B29', { observed: { ...wrote, cards: [] }, decided: 'none', record: { checked: '', ok: true } })).verdict).toBe('FAIL');
  });

  it('fails a write whose card ran another operation than the one the item asks for', () => {
    const disabled = {
      ...observe([]),
      cards: [{ operation: 'base.app.disable', risk: 'normal', confirmWord: '' }],
      executed: [{ name: 'base.app.disable', kind: 'command', outcome: 'ok', code: '' }],
    };
    const off = { checked: 'Reservations is off', ok: true };
    expect(verdictOf(outcome('B28b', { observed: disabled, decided: 'confirmed', record: off })).verdict).toBe('PASS');
    const v = verdictOf(outcome('B28c', { observed: disabled, decided: 'confirmed', record: off }));
    expect(v.verdict).toBe('FAIL');
    expect(v.reasons.join(' ')).toMatch(/base\.app\.enable did not run/);
  });

  it('fails a write whose confirmed card then failed, even when a later card did the job', () => {
    const retried = {
      ...observe([]),
      cards: [
        { operation: 'staff.member.create', risk: 'normal', confirmWord: '' },
        { operation: 'staff.member.create', risk: 'normal', confirmWord: '' },
      ],
      executed: [
        { name: 'staff.member.create', kind: 'command', outcome: 'error', code: 'invalid_payload' },
        { name: 'staff.member.create', kind: 'command', outcome: 'ok', code: '' },
      ],
    };
    const v = verdictOf(outcome('B30', { observed: retried, decided: 'confirmed', record: { checked: 'Luis QA listed', ok: true } }));
    expect(v.verdict).toBe('FAIL');
    expect(v.reasons.join(' ')).toMatch(/staff\.member\.create failed \(invalid_payload\)/);
    const cancelled = { ...retried, executed: [{ name: 'customer.customer.create', kind: 'command', outcome: 'cancelled', code: 'x' }] };
    const done = { decided: 'cancelled' as const, record: { checked: 'not created', ok: true } };
    expect(verdictOf(outcome('C36', { ...done, observed: cancelled })).verdict).toBe('PASS');
    // Cancelled (its card counts), then a retry refused before any card: nothing failed after a card.
    const cancelledThenRefused = {
      ...observe([]),
      cards: [{ operation: 'customer.customer.create', risk: 'normal', confirmWord: '' }],
      executed: [
        { name: 'customer.customer.create', kind: 'command', outcome: 'cancelled', code: 'base.assistant_not_confirmed' },
        { name: 'customer.customer.create', kind: 'command', outcome: 'error', code: 'invalid_payload' },
      ],
    };
    expect(verdictOf(outcome('C36', { ...done, observed: cancelledThenRefused })).verdict).toBe('PASS');
    // Refused before any card (the data did not fit), then asked again right: one card, one yes, nothing failed after it.
    const refusedFirst = { ...retried, cards: [retried.cards[0]] };
    expect(verdictOf(outcome('B30', { observed: refusedFirst, decided: 'confirmed', record: { checked: 'Luis QA listed', ok: true } })).verdict).toBe('PASS');
  });

  it('fails an answer that shows a blockquote as a raw «>» line', () => {
    const v = verdictOf(outcome('B25', { answer: 'Abre la caja.\n> ⚠️ Cuenta el efectivo antes.' }));
    expect(v.verdict).toBe('FAIL');
    expect(v.reasons.join(' ')).toMatch(/blockquote/);
    expect(verdictOf(outcome('B25', { answer: 'Abre la caja. 5 > 3 no es una cita.' })).verdict).toBe('PASS');
  });

  it('passes «what did I sell today» with a read and no write, and fails it with a write', () => {
    const read = { ...observe([]), executed: [{ name: 'sale.sale.list', kind: 'query', outcome: 'ok', code: '' }] };
    expect(verdictOf(outcome('B32', { observed: read })).verdict).toBe('PASS');
    const wrote = { ...read, executed: [...read.executed, { name: 'sale.sale.create', kind: 'command', outcome: 'ok', code: '' }] };
    expect(verdictOf(outcome('B32', { observed: wrote })).verdict).toBe('FAIL');
    expect(verdictOf(outcome('B32', { observed: observe(HOWTO) })).verdict).toBe('FAIL');
  });

  it('passes the other-scope question when it cites the plans or points to erplora.com, never with a write', () => {
    const plans = { ...observe(HOWTO), citations: [{ source: 'plans', path: 'plans', heading: 'Starter', lang: 'es' }] };
    expect(verdictOf(outcome('B34', { observed: plans })).verdict).toBe('PASS');
    expect(verdictOf(outcome('B34', { answer: 'Míralo en erplora.com, en Facturación.' })).verdict).toBe('PASS');
    expect(verdictOf(outcome('B34', { answer: 'Pagas 29 € al mes.' })).verdict).toBe('FAIL');
  });

  it('passes the allowance only when one question spent exactly one message and the foot moved with the next one', () => {
    const foot = { footBefore: 'You have 5 of 30 messages left this month.', footAfter: 'You have 4 of 30 messages left this month.' };
    expect(verdictOf(outcome('C35', { usage: { before: 3, after: 4, ...foot } })).verdict).toBe('PASS');
    expect(verdictOf(outcome('C35', { usage: { before: 3, after: 3, ...foot } })).verdict).toBe('FAIL');
    expect(verdictOf(outcome('C35')).verdict).toBe('FAIL');
    const still = verdictOf(outcome('C35', { usage: { before: 3, after: 4, footBefore: foot.footBefore, footAfter: foot.footBefore } }));
    expect(still.verdict).toBe('FAIL');
    expect(still.reasons.join(' ')).toMatch(/foot/);
    expect(verdictOf(outcome('C35', { usage: { before: 3, after: 4, footBefore: '', footAfter: '' } })).verdict).toBe('FAIL');
  });

  it('fails a cancelled card followed by the «it said it made a change» notice', () => {
    const asked = { ...observe([]), cards: [{ operation: 'customer.customer.create', risk: 'normal', confirmWord: '' }] };
    const done = { decided: 'cancelled' as const, observed: asked, record: { checked: 'not created', ok: true } };
    expect(verdictOf(outcome('C36', done)).verdict).toBe('PASS');
    expect(verdictOf(outcome('C36', { ...done, notices: ['claimed_change'] })).verdict).toBe('FAIL');
    expect(verdictOf(outcome('C36', { ...done, record: { checked: 'created anyway', ok: false } })).verdict).toBe('FAIL');
  });

  it('passes «turn Customers on» when the app ends on, by its card or because it already was, and fails it otherwise', () => {
    const on = { checked: 'Customers is on', ok: true };
    expect(verdictOf(outcome('B28', { observed: observe([]), record: on })).verdict).toBe('PASS');
    const enabled = {
      ...observe([]),
      cards: [{ operation: 'base.app.enable', risk: 'normal', confirmWord: '' }],
      executed: [{ name: 'base.app.enable', kind: 'command', outcome: 'ok', code: '' }],
    };
    expect(verdictOf(outcome('B28', { observed: enabled, decided: 'confirmed', record: on })).verdict).toBe('PASS');
    expect(verdictOf(outcome('B28', { observed: observe([]), record: { checked: 'Customers is off', ok: false } })).verdict).toBe('FAIL');
    const refused = { ...enabled, executed: [{ name: 'base.app.enable', kind: 'command', outcome: 'error', code: 'x' }] };
    expect(verdictOf(outcome('B28', { observed: refused, decided: 'confirmed', record: on })).verdict).toBe('FAIL');
    const blind = { ...observe([]), executed: enabled.executed };
    expect(verdictOf(outcome('B28', { observed: blind, record: on })).verdict).toBe('FAIL');
  });

  it('passes the English how-to only when the answer is in English and cites English docs', () => {
    const english = { ...observe(HOWTO), citations: [{ source: 'app_doc', path: 'staff/README.md', heading: 'Team', lang: 'en' }] };
    const answer = 'Open Team, tap Add and type the PIN of the employee. Then save it and the employee can sign in.';
    expect(verdictOf(outcome('C37', { observed: english, answer })).verdict).toBe('PASS');
    expect(verdictOf(outcome('C37', { observed: english })).verdict).toBe('FAIL');
    expect(verdictOf(outcome('C37', { answer })).verdict).toBe('FAIL');
  });
});

describe('renderReport', () => {
  it('has one section per item with its question, whole answer, tools, card, citations, verdict and screenshot', () => {
    const text = renderReport([outcome('B21', { answer: 'Línea 1 | con barra\nLínea 2' })], {
      run: 'r1',
      model: 'qwen/qwen3.7-plus',
      fallback: 'openai/gpt-5.4-mini',
      service: 'openai',
      chunks: { help: 10, app_doc: 20 },
    });
    expect(text).toContain('## B21');
    expect(text).toContain('¿Cómo doy de alta a un empleado con su PIN?');
    expect(text).toContain('Línea 1 \\| con barra<br>Línea 2');
    expect(text).toContain('base.docs.search (query, ok)');
    expect(text).toContain('staff/README.md › Equipo › Alta (es)');
    expect(text).toContain('PASS');
    expect(text).toContain('/tmp/B21.png');
    expect(text).toContain('qwen/qwen3.7-plus');
    expect(text).toMatch(/help 10 · app_doc 20 \(total 30\)/);
  });

  it('lists the items that did not run', () => {
    expect(renderReport([], { run: 'r', model: '', fallback: '', service: '', chunks: {} })).toMatch(/Not run: B21, B22/);
  });
});

describe('redact', () => {
  it('takes every secret out of a text, whatever surrounds it', () => {
    expect(redact('key=sk-abc123 and sk-abc123.', ['sk-abc123', ''])).toBe('key=[redacted] and [redacted].');
  });
});

describe('seedCommand', () => {
  const env = { QA_QWEN_API_KEY: 'sk-qwen-secret', QA_OPENAI_API_KEY: 'sk-openai-secret', PATH: '/bin' };

  it('runs the seed in the SaaS on its database with the keys in the environment, never in the arguments', () => {
    const command = seedCommand(env, 'saas_e2e_8895');
    expect(command.file).toBe('uv');
    expect(command.args.slice(0, 5)).toEqual(['run', 'python', 'manage.py', 'shell', '-c']);
    expect(command.args.join(' ')).not.toMatch(/sk-qwen-secret|sk-openai-secret/);
    expect(command.env).toMatchObject({ DB_NAME: 'saas_e2e_8895', ASSISTANT_SERVICE_PROVIDER: 'openai', ...env });
  });

  it('refuses without a key, naming the variable and never a value', () => {
    expect(() => seedCommand({ QA_OPENAI_API_KEY: 'sk-openai-secret' }, 'saas_e2e_8895')).toThrow(/QA_QWEN_API_KEY/);
    expect(() => seedCommand({ QA_QWEN_API_KEY: 'sk-qwen-secret' }, 'saas_e2e_8895')).toThrow(/QA_OPENAI_API_KEY/);
  });

  it('sets the providers only through the SaaS operations and prints no key', () => {
    for (const op of ['credential_import', 'credential_save', 'model_select', 'policy_update']) expect(SEED_PY).toContain(`services.${op}(`);
    expect(SEED_PY).not.toMatch(/print\([^)]*(key|KEY)/);
    expect(SEED_PY).not.toMatch(/cursor|raw\(/);
    const parsed = spawnSync('python3', ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: SEED_PY, encoding: 'utf8' });
    expect(parsed.status, parsed.stderr).toBe(0);
  });
});
