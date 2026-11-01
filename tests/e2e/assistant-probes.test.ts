// @vitest-environment node
// The pure parts of layer 2 of the assistant's QA (docs plan 2026-10-31, the assistant's knowledge and QA, §1.5): the
// probe files a QA agent writes (a NEW natural phrase per tool, role and language), how each probe is checked against
// the catalogue `manage.py export_assistant_catalog` exports, the verdict of a turn with the real model, the report,
// the skeleton generator (`pnpm qa:probes`) and the SaaS seed of a manager and an admin of `a`. The spec
// (qa/assistant-probes.spec.ts) only runs with QA_REAL_PROVIDER=1, never in CI.
import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { observe, type Observed } from './assistant-battery';
import {
  type Catalog,
  catalogKey,
  catalogsNeeded,
  chosenTool,
  DECISIONS,
  EXPECTS,
  LANGUAGES,
  loadedProbes,
  MEMBERS,
  MEMBERS_PY,
  membersCommand,
  parseProbeFile,
  type Probe,
  type ProbeOutcome,
  probeVerdict,
  problemsOf,
  renderProbeReport,
  ROLES,
  runCli,
  saysCannot,
  skeleton,
  type Tool,
} from './assistant-probes';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const sse = (...frames: object[]): string => frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('');

const tool = (name: string, kind: 'read' | 'write', asks: string[] = [], risk = 'normal'): Tool => ({
  name,
  tool_name: name.replace(/\./g, '__'),
  app_label: name.split('.')[0],
  kind,
  permission: `${name.split('.')[0]}.x`,
  risk,
  description: `What ${name} does.`,
  asks,
  input_schema: {},
});

const OWNER_ES: Catalog = [
  tool('base.app.disable', 'write', ['quita la app de reservas', 'apaga Reservas']),
  tool('base.docs.search', 'read', ['¿cómo se hace…?', '¿dónde está…?']),
  tool('customer.customer.create', 'write', ['apúntame a Ana', 'nuevo cliente Luis']),
  tool('customer.customer.delete', 'write', ['borra a Marta', 'quita a ese cliente'], 'high'),
  tool('customer.customer.list', 'read', ['¿qué clientes tengo?', 'búscame a Ana']),
  tool('sale.department.create', 'write', ['crea la sección bebidas', 'nueva familia postres']),
  tool('sale.sale.list', 'read', ['las ventas de ayer', 'enséñame los tickets']),
  tool('sale.sale.today', 'read', ['¿cuánto llevo hoy?', '¿qué he vendido hoy?']),
];
const EMPLOYEE_ES: Catalog = OWNER_ES.filter((row) =>
  ['base.docs.search', 'customer.customer.create', 'customer.customer.list', 'sale.sale.list'].includes(row.name),
);
const CATALOGS: Record<string, Catalog> = {
  [catalogKey('owner', 'es')]: OWNER_ES,
  [catalogKey('employee', 'es')]: EMPLOYEE_ES,
};

const probe = (overrides: Partial<Probe> = {}): Probe => ({
  id: 'owner.es.sale.sale.today',
  app: 'sale',
  tool: 'sale.sale.today',
  role: 'owner',
  language: 'es',
  phrase: '¿y hoy qué tal vamos de caja?',
  expect: 'read',
  ...overrides,
});

const file = (...probes: object[]) => JSON.stringify({ probes });

const executed = (name: string, kind: 'query' | 'command', outcome = 'ok', call = 'c1') => ({
  type: 'executed',
  call_id: call,
  name,
  app: name.split('.')[0],
  kind,
  outcome,
  code: '',
});
const DOCS = JSON.stringify({ results: [{ source: 'help', path: 'help/pin.md', heading: 'PIN', text: '…', lang: 'es' }] });

function outcome(p: Probe, observed: Observed, overrides: Partial<ProbeOutcome> = {}): ProbeOutcome {
  return { probe: p, answer: 'Hoy llevas 120,00 €.', observed, decided: 'none', notices: [], screenshot: `/tmp/${p.id}.png`, problems: [], ...overrides };
}

describe('parseProbeFile', () => {
  it('reads the probes of a file, with their optional decision and notes', () => {
    const card = probe({ id: 'owner.es.customer.customer.create', app: 'customer', tool: 'customer.customer.create', expect: 'card', decide: 'confirm', notes: 'seeded' });
    expect(parseProbeFile(file(probe(), card), 'a.json')).toEqual([probe(), card]);
  });

  it('accepts an empty phrase (a skeleton still to fill): the run says so per probe', () => {
    expect(parseProbeFile(file(probe({ phrase: '' })), 'a.json')[0].phrase).toBe('');
  });

  it('refuses what is not a probe file, naming the file and the probe', () => {
    expect(() => parseProbeFile('[]', 'a.json')).toThrow(/a\.json: .*"probes"/);
    expect(() => parseProbeFile('{', 'a.json')).toThrow(/a\.json: not JSON/);
    expect(() => parseProbeFile(file({ ...probe(), role: 'boss' }), 'a.json')).toThrow(/a\.json, probe 1 .*role.*boss/);
    expect(() => parseProbeFile(file({ ...probe(), language: 'fr' }), 'a.json')).toThrow(/language/);
    expect(() => parseProbeFile(file({ ...probe(), expect: 'maybe' }), 'a.json')).toThrow(/expect/);
    expect(() => parseProbeFile(file({ ...probe(), id: 'Bad Id' }), 'a.json')).toThrow(/id/);
    const noPhrase: Partial<Probe> = probe();
    delete noPhrase.phrase;
    expect(() => parseProbeFile(file(noPhrase), 'a.json')).toThrow(/phrase/);
    expect(() => parseProbeFile(file({ ...probe(), extra: 1 }), 'a.json')).toThrow(/extra/);
  });

  it('takes a decision only on a card, and only cancel or confirm', () => {
    expect(() => parseProbeFile(file(probe({ decide: 'confirm' })), 'a.json')).toThrow(/decide.*card/);
    expect(() => parseProbeFile(file({ ...probe({ expect: 'card' }), decide: 'yes' }), 'a.json')).toThrow(/decide/);
  });
});

describe('loadedProbes', () => {
  it('joins the files in order and refuses an id used twice, naming both files', () => {
    const other = probe({ id: 'employee.es.sale.sale.list', role: 'employee', tool: 'sale.sale.list' });
    expect(loadedProbes([{ source: 'a.json', text: file(probe()) }, { source: 'b.json', text: file(other) }]).map((p) => p.id)).toEqual([
      probe().id,
      other.id,
    ]);
    expect(() => loadedProbes([{ source: 'a.json', text: file(probe()) }, { source: 'b.json', text: file(probe()) }])).toThrow(
      /owner\.es\.sale\.sale\.today.*a\.json.*b\.json/,
    );
  });
});

describe('catalogsNeeded', () => {
  it('asks for each role and language once, and for the owner of every language (the refused ones are the owner’s)', () => {
    const probes = [probe(), probe({ id: 'x', role: 'employee' }), probe({ id: 'y', role: 'employee', language: 'en' })];
    expect(catalogsNeeded(probes)).toEqual([
      { role: 'employee', language: 'en' },
      { role: 'employee', language: 'es' },
      { role: 'owner', language: 'en' },
      { role: 'owner', language: 'es' },
    ]);
  });
});

describe('problemsOf', () => {
  it('has none for a well-written probe of each kind', () => {
    expect(problemsOf(probe(), CATALOGS)).toEqual([]);
    expect(problemsOf(probe({ app: 'customer', tool: 'customer.customer.create', expect: 'card', phrase: 'mete a Pepa en clientes' }), CATALOGS)).toEqual([]);
    const refused = probe({ role: 'employee', app: 'customer', tool: 'customer.customer.delete', expect: 'refused', phrase: 'quítame a Marta de la lista' });
    expect(problemsOf(refused, CATALOGS)).toEqual([]);
    expect(problemsOf(probe({ app: 'base', tool: 'base.docs.search', expect: 'docs', phrase: '¿y el PIN cómo va?' }), CATALOGS)).toEqual([]);
  });

  it('wants the phrase written', () => {
    expect(problemsOf(probe({ phrase: '  ' }), CATALOGS)).toEqual(['the phrase is empty: write how a person of the role would ask']);
  });

  it('refuses a copy of one of the tool’s asks, whatever the case or the spaces', () => {
    expect(problemsOf(probe({ phrase: '  ¿Cuánto   LLEVO hoy? ' }), CATALOGS)).toEqual([
      'the phrase is one of the asks of sale.sale.today («¿cuánto llevo hoy?»): write a new one',
    ]);
  });

  it('refuses a copy of an ask of the other language too, when its catalogue is there', () => {
    const owner = (asks: string[]) => OWNER_ES.map((row) => (row.name === 'sale.sale.today' ? { ...row, asks } : row));
    const both = { ...CATALOGS, [catalogKey('owner', 'en')]: owner(['what did we take today?', 'today’s sales']) };
    expect(problemsOf(probe({ phrase: 'What did we take today?' }), both)).toEqual([
      'the phrase is one of the asks of sale.sale.today («what did we take today?»): write a new one',
    ]);
  });

  it('wants the role to hold the docs search for a «docs» probe', () => {
    const blind = { ...CATALOGS, [catalogKey('employee', 'es')]: EMPLOYEE_ES.filter((row) => row.name !== 'base.docs.search') };
    const docs = probe({ role: 'employee', app: 'base', tool: 'base.docs.search', expect: 'docs', phrase: '¿y el PIN?' });
    expect(problemsOf(docs, blind)).toEqual(['the employee does not hold base.docs.search']);
  });

  it('says when a catalogue the probe needs was not exported', () => {
    expect(problemsOf(probe({ language: 'en' }), CATALOGS)).toEqual(['no catalogue of the owner in en']);
  });

  it('names a tool the Hub does not have, or of another app', () => {
    expect(problemsOf(probe({ tool: 'sale.sale.yesterday' }), CATALOGS)).toEqual(['no tool sale.sale.yesterday in the owner’s catalogue']);
    expect(problemsOf(probe({ app: 'customer' }), CATALOGS)).toEqual(['sale.sale.today is a tool of sale, not of customer']);
  });

  it('wants a read for «read» and a write for «card»', () => {
    expect(problemsOf(probe({ app: 'customer', tool: 'customer.customer.create', phrase: 'mete a Pepa' }), CATALOGS)).toEqual([
      'customer.customer.create is a write: expect «card», not «read»',
    ]);
    expect(problemsOf(probe({ expect: 'card' }), CATALOGS)).toEqual(['sale.sale.today is a read: expect «read», not «card»']);
  });

  it('wants the role to hold the tool it reads or writes, and to lack the one it is refused', () => {
    expect(problemsOf(probe({ role: 'employee' }), CATALOGS)).toEqual([
      'the employee does not hold sale.sale.today: expect «refused»',
    ]);
    expect(problemsOf(probe({ role: 'employee', tool: 'sale.sale.list', expect: 'refused' }), CATALOGS)).toEqual([
      'the employee holds sale.sale.list: it is not refused',
    ]);
  });

  it('wants base.docs.search for «docs»', () => {
    expect(problemsOf(probe({ expect: 'docs' }), CATALOGS)).toEqual(['a «docs» probe is of base.docs.search, not of sale.sale.today']);
  });
});

describe('saysCannot', () => {
  it('hears a refusal in Spanish and in English', () => {
    expect(saysCannot('Lo siento, no puedo borrar clientes: no tienes permiso.', 'es')).toBe(true);
    expect(saysCannot('Eso solo lo puede hacer el dueño del negocio.', 'es')).toBe(true);
    expect(saysCannot('No tienes acceso a las estadísticas de ventas.', 'es')).toBe(true);
    expect(saysCannot("Sorry, I can't do that: your role doesn't allow it.", 'en')).toBe(true);
    expect(saysCannot('Only the owner or an admin can turn apps off.', 'en')).toBe(true);
    expect(saysCannot('You do not have permission to delete customers.', 'en')).toBe(true);
  });

  it('does not hear one in an answer that just answers', () => {
    expect(saysCannot('Hoy llevas 120,00 € en 5 tickets.', 'es')).toBe(false);
    expect(saysCannot('You sold 120.00 € today in 5 tickets.', 'en')).toBe(false);
    expect(saysCannot('', 'es')).toBe(false);
  });
});

describe('probeVerdict', () => {
  const read = observe([sse(executed('base.business.get', 'query'), executed('sale.sale.today', 'query', 'ok', 'c2'))]);

  it('passes a read that ran its tool with no card, and names the tool chosen', () => {
    expect(probeVerdict(outcome(probe(), read))).toEqual({ verdict: 'PASS', reasons: [], chosen: 'sale.sale.today' });
  });

  it('fails a read that ran another tool, or showed a card', () => {
    const other = observe([sse(executed('sale.sale.list', 'query'))]);
    expect(probeVerdict(outcome(probe(), other))).toMatchObject({ verdict: 'FAIL', chosen: 'sale.sale.list', reasons: ['sale.sale.today did not run (ran: sale.sale.list)'] });
    const card = { operation: 'sale.department.create', risk: 'normal', confirm_word: '' };
    const carded = observe([sse(executed('sale.sale.today', 'query'), { type: 'confirm', card, call: {} })]);
    expect(probeVerdict(outcome(probe(), carded, { decided: 'cancelled' })).reasons).toEqual(['a card was shown: sale.department.create']);
  });

  it('is n.a. when the probe itself is wrong, whatever the turn did', () => {
    expect(probeVerdict(outcome(probe(), read, { problems: ['the phrase is empty: write how a person of the role would ask'] }))).toEqual({
      verdict: 'N/A',
      reasons: ['the phrase is empty: write how a person of the role would ask'],
      chosen: 'none',
    });
  });

  it('fails a turn that ended with an error or with no answer', () => {
    const failed = observe([sse(executed('sale.sale.today', 'query'), { type: 'error', code: 'assistant.cut' })]);
    expect(probeVerdict(outcome(probe(), failed, { answer: '' })).reasons).toEqual(['the turn ended with the error assistant.cut', 'no answer']);
  });

  const create = probe({ id: 'c', app: 'customer', tool: 'customer.customer.create', expect: 'card', phrase: 'mete a Pepa' });
  const cardOf = (operation: string) => ({ type: 'confirm', card: { operation, risk: 'normal', confirm_word: '' }, call: {} });

  it('passes a card of its tool that was cancelled and wrote nothing', () => {
    const seen = observe([sse(cardOf('customer.customer.create')), sse(executed('customer.customer.create', 'command', 'cancelled'))]);
    expect(probeVerdict(outcome(create, seen, { decided: 'cancelled' }))).toEqual({ verdict: 'PASS', reasons: [], chosen: 'customer.customer.create' });
  });

  it('fails a card of another tool, no card, or a cancelled card that still wrote', () => {
    const other = observe([sse(cardOf('customer.customer.update'))]);
    expect(probeVerdict(outcome(create, other, { decided: 'cancelled' })).reasons).toEqual([
      'no card of customer.customer.create (cards: customer.customer.update)',
    ]);
    expect(probeVerdict(outcome(create, observe([sse({ type: 'text', text: '¿Qué teléfono?' })]))).reasons).toEqual([
      'no card of customer.customer.create (cards: none)',
      'the card was not cancelled',
    ]);
    const wrote = observe([sse(cardOf('customer.customer.create')), sse(executed('customer.customer.create', 'command', 'ok'))]);
    expect(probeVerdict(outcome(create, wrote, { decided: 'cancelled' })).reasons).toEqual(['a write ran: customer.customer.create']);
  });

  it('passes a confirmed card when its write reports success, and fails it otherwise', () => {
    const confirm = { ...create, decide: 'confirm' as const };
    const done = observe([sse(cardOf('customer.customer.create')), sse(executed('customer.customer.create', 'command', 'ok'))]);
    expect(probeVerdict(outcome(confirm, done, { decided: 'confirmed' })).verdict).toBe('PASS');
    const failed = observe([sse(cardOf('customer.customer.create')), sse({ ...executed('customer.customer.create', 'command', 'error'), code: 'invalid_payload' })]);
    expect(probeVerdict(outcome(confirm, failed, { decided: 'confirmed' })).reasons).toEqual([
      'customer.customer.create did not report success after its card (error invalid_payload)',
    ]);
    expect(probeVerdict(outcome(confirm, done, { decided: 'cancelled' })).reasons).toEqual(['the card was not confirmed']);
    const twice = observe([sse(cardOf('customer.customer.create')), sse(executed('customer.customer.create', 'command'), executed('customer.tag.create', 'command', 'ok', 'c2'))]);
    expect(probeVerdict(outcome(confirm, twice, { decided: 'confirmed' })).reasons).toEqual(['another write ran: customer.tag.create']);
  });

  const refused = probe({ id: 'r', role: 'employee', app: 'customer', tool: 'customer.customer.delete', expect: 'refused', phrase: 'quita a Marta' });

  it('passes a refusal: no tool of the business ran, no card, and the answer says it cannot', () => {
    const seen = observe([sse(executed('base.setup.status', 'query'), { type: 'text', text: 'No puedo: no tienes permiso.' })]);
    expect(probeVerdict(outcome(refused, seen, { answer: 'No puedo: no tienes permiso.' }))).toEqual({ verdict: 'PASS', reasons: [], chosen: 'none' });
    const tried = observe([sse(executed('customer.customer.delete', 'command', 'refused'))]);
    expect(probeVerdict(outcome(refused, tried, { answer: 'No tienes permiso para borrar clientes.' })).verdict).toBe('PASS');
  });

  it('fails a refusal that showed a card', () => {
    const card = { type: 'confirm', card: { operation: 'customer.customer.delete', risk: 'high', confirm_word: 'BORRAR' }, call: {} };
    expect(probeVerdict(outcome(refused, observe([sse(card)]), { answer: 'No puedo.', decided: 'cancelled' })).reasons).toEqual([
      'a card was shown: customer.customer.delete',
    ]);
  });

  it('fails a refusal that ran a tool of the business or never says it cannot', () => {
    const seen = observe([sse(executed('customer.customer.list', 'query'))]);
    expect(probeVerdict(outcome(refused, seen, { answer: 'Marta está en tu lista.' })).reasons).toEqual([
      'a tool of the business ran: customer.customer.list',
      'the answer does not say it cannot',
    ]);
  });

  it('passes a docs probe that searched and cited, and fails one that did not', () => {
    const docs = probe({ id: 'd', app: 'base', tool: 'base.docs.search', expect: 'docs', phrase: '¿y el PIN?' });
    const searched = observe([sse(executed('base.docs.search', 'query'), { type: 'done', append: [{ role: 'tool', tool_call_id: 'c1', content: DOCS }] })]);
    expect(probeVerdict(outcome(docs, searched))).toEqual({ verdict: 'PASS', reasons: [], chosen: 'base.docs.search' });
    const empty = observe([sse(executed('base.docs.search', 'query'))]);
    expect(probeVerdict(outcome(docs, empty)).reasons).toEqual(['base.docs.search returned no excerpt']);
    expect(probeVerdict(outcome(docs, observe([]))).reasons).toEqual(['base.docs.search did not run']);
  });
});

describe('chosenTool', () => {
  it('is the card of a write, else the first tool of the business that ran, else the docs, else none', () => {
    const lookedUp = observe([sse(executed('customer.customer.by_phone', 'query'), { type: 'confirm', card: { operation: 'customer.customer.create' }, call: {} })]);
    expect(chosenTool(lookedUp)).toBe('customer.customer.create');
    expect(chosenTool(observe([sse(executed('base.setup.status', 'query'), executed('sale.sale.list', 'query', 'ok', 'c2'))]))).toBe('sale.sale.list');
    expect(chosenTool(observe([sse({ type: 'confirm', card: { operation: 'base.app.disable' }, call: {} })]))).toBe('base.app.disable');
    expect(chosenTool(observe([sse(executed('base.docs.search', 'query'))]))).toBe('base.docs.search');
    expect(chosenTool(observe([sse(executed('base.setup.status', 'query'))]))).toBe('none');
  });
});

describe('renderProbeReport', () => {
  const read = observe([sse(executed('sale.sale.today', 'query'))]);
  const meta = { run: 'r1', model: 'qwen/qwen3.7-plus', fallback: 'openai/gpt-5.4-mini', service: 'openai', files: ['tests/e2e/qa/probes/core.json'] };

  it('counts the verdicts and lists each probe with the tool chosen and the start of the answer', () => {
    const long = `Hoy | llevas\n${'x'.repeat(400)}`;
    const report = renderProbeReport(
      [
        outcome(probe(), read, { answer: long }),
        outcome(probe({ id: 'n', phrase: '' }), observe([]), { problems: ['the phrase is empty: write how a person of the role would ask'] }),
      ],
      meta,
    );
    expect(report).toContain('- Run: r1');
    expect(report).toContain('- Answering model: qwen/qwen3.7-plus · fallback: openai/gpt-5.4-mini · embeddings: openai');
    expect(report).toContain('- Probe files: tests/e2e/qa/probes/core.json');
    expect(report).toContain('- Verdicts: PASS 1 · FAIL 0 · N/A 1');
    expect(report).toContain(`| owner.es.sale.sale.today | owner | es | read | PASS | sale.sale.today | ¿y hoy qué tal vamos de caja? | Hoy \\| llevas<br>${'x'.repeat(287)} |`);
    expect(report).toContain('| n | owner | es | read | N/A | none |  |');
    expect(report).toContain('- **n** (N/A): the phrase is empty: write how a person of the role would ask — screenshot /tmp/n.png');
    const confirmed = probe({ id: 'c', app: 'customer', tool: 'customer.customer.create', expect: 'card', decide: 'confirm' });
    expect(renderProbeReport([outcome(confirmed, observe([]))], meta)).toContain('| c | owner | es | card (confirm) | FAIL | none |');
  });
});

describe('skeleton', () => {
  const options = { role: 'employee' as const, language: 'es' as const, sample: 1, all: false, seed: 7, docs: 1 };

  it('samples tools per app of the role, derives what to expect, adds the refused ones and a docs probe, with empty phrases', () => {
    const made = skeleton(EMPLOYEE_ES, OWNER_ES, options);
    expect(made.generated).toEqual({ role: 'employee', language: 'es', apps: ['base', 'customer', 'sale'], sample: 1, all: false, seed: 7 });
    // The tools every turn is offered (base.docs.search and the like) are never sampled: «docs» probes ask the docs.
    const kinds = made.probes.map((p) => `${p.app} ${['read', 'card'].includes(p.expect) ? 'tool' : p.expect}`);
    expect(kinds).toEqual(['base docs', 'base refused', 'customer tool', 'customer refused', 'sale tool', 'sale refused']);
    for (const p of made.probes) {
      expect(p.phrase).toBe('');
      expect(p.role).toBe('employee');
      expect(p.language).toBe('es');
      expect(p.decide).toBeUndefined();
      expect(p.notes).toBe(OWNER_ES.find((row) => row.name === p.tool)?.description);
      if (p.expect === 'refused') expect(EMPLOYEE_ES.some((row) => row.name === p.tool)).toBe(false);
      else expect(EMPLOYEE_ES.some((row) => row.name === p.tool)).toBe(true);
    }
    expect(new Set(made.probes.map((p) => p.id)).size).toBe(made.probes.length);
    expect(made.probes.find((p) => p.expect === 'docs')).toMatchObject({ id: 'employee.es.base.docs.search', tool: 'base.docs.search' });
  });

  it('is the same for the same seed, and mixes reads and writes when it takes two', () => {
    expect(skeleton(EMPLOYEE_ES, OWNER_ES, options)).toEqual(skeleton(EMPLOYEE_ES, OWNER_ES, options));
    const owner = skeleton(OWNER_ES, OWNER_ES, { ...options, role: 'owner', sample: 2, docs: 0 });
    const sale = owner.probes.filter((p) => p.app === 'sale').map((p) => p.expect).sort();
    expect(sale).toEqual(['card', 'read']);
    expect(owner.probes.some((p) => p.expect === 'refused')).toBe(false);
  });

  it('numbers a second docs probe instead of repeating its id', () => {
    const made = skeleton(EMPLOYEE_ES, OWNER_ES, { ...options, docs: 2 });
    expect(made.probes.filter((p) => p.expect === 'docs').map((p) => p.id)).toEqual(['employee.es.base.docs.search', 'employee.es.base.docs.search-2']);
  });

  it('takes every tool with --all', () => {
    const all = skeleton(EMPLOYEE_ES, OWNER_ES, { ...options, all: true });
    expect(all.probes.map((p) => p.tool).sort()).toEqual(OWNER_ES.map((row) => row.name).sort());
  });

  it('gives each probe a file the spec reads', () => {
    const made = skeleton(EMPLOYEE_ES, OWNER_ES, options);
    expect(parseProbeFile(JSON.stringify(made), 'skeleton.json')).toEqual(made.probes);
  });
});

describe('runCli (pnpm qa:probes)', () => {
  function deps() {
    const exported: string[] = [];
    const written: Record<string, string> = {};
    const said: string[] = [];
    return {
      exported,
      written,
      said,
      deps: {
        exportCatalog: (role: string, language: string, apps: string[]) => {
          exported.push(`${role}/${language}/${apps.join(',')}`);
          return role === 'owner' ? OWNER_ES : EMPLOYEE_ES;
        },
        write: (path: string, text: string) => void (written[path] = text),
        print: (line: string) => void said.push(line),
        fail: (line: string) => void said.push(`ERR ${line}`),
        now: () => 42,
      },
    };
  }

  it('exports the role’s catalogue and the owner’s, writes the skeleton and says what to do next', () => {
    const run = deps();
    expect(runCli(['--role', 'employee', '--language', 'es', '--apps', 'sale,customer', '--sample', '1', '--out', 'x.json'], run.deps)).toBe(0);
    expect(run.exported).toEqual(['employee/es/sale,customer', 'owner/es/sale,customer']);
    const made = JSON.parse(run.written['x.json']) as { probes: Probe[]; generated: { seed: number } };
    expect(made.generated.seed).toBe(42);
    expect(made.probes.length).toBeGreaterThan(0);
    expect(run.said.join('\n')).toMatch(/x\.json: \d+ probes .*write each phrase/);
  });

  it('exports once for the owner and writes under .artifacts by default', () => {
    const run = deps();
    expect(runCli(['--role', 'owner', '--language', 'es', '--all', '--seed', '3'], run.deps)).toBe(0);
    expect(run.exported).toEqual(['owner/es/']);
    expect(Object.keys(run.written)).toEqual([join('tests', 'e2e', '.artifacts', 'qa', 'probes-owner-es-3.json')]);
  });

  it('refuses a wrong call with its usage, and a failed export with its message', () => {
    for (const args of [[], ['--role', 'boss', '--language', 'es'], ['--role', 'owner', '--language', 'fr'], ['--role', 'owner', '--language', 'es', '--sample', '0'], ['--role', 'owner', '--language', 'es', '--seed', '-1'], ['--role', 'owner', '--language', 'es', '--docs', 'x'], ['--role', 'owner', '--language', 'es', '--what'], ['--role', 'owner', '--language']]) {
      const run = deps();
      expect(runCli(args, run.deps), args.join(' ')).toBe(2);
      expect(run.said.join('\n')).toMatch(/ERR .*Usage: pnpm qa:probes/);
    }
    const run = deps();
    run.deps.exportCatalog = () => {
      throw new Error('Unknown app(s): sails.');
    };
    expect(runCli(['--role', 'owner', '--language', 'es', '--apps', 'sails'], run.deps)).toBe(1);
    expect(run.said).toEqual(['ERR qa:probes: Unknown app(s): sails.']);
  });
});

describe('membersCommand', () => {
  it('seeds a manager and an admin of a on the stack’s SaaS, development only', () => {
    expect(MEMBERS.manager).toEqual({ email: 'qa-manager@example.com', password: 'manager' });
    expect(MEMBERS.admin).toEqual({ email: 'qa-admin@example.com', password: 'admin' });
    expect(MEMBERS_PY).toContain('if not settings.DEBUG');
    expect(MEMBERS_PY).toContain('seed_demo_business("a"');
    expect(MEMBERS_PY).toContain('HubMember.Role.MANAGER');
    expect(MEMBERS_PY).toContain('HubMember.Role.ADMIN');
    const command = membersCommand({ PATH: '/bin', DB_NAME: 'hub_e2e_1' }, 'saas_e2e_2');
    expect(command.file).toBe('uv');
    expect(command.args.slice(0, 5)).toEqual(['run', 'python', 'manage.py', 'shell', '-c']);
    expect(command.env.DB_NAME).toBe('saas_e2e_2');
    expect(command.env.PATH).toBe('/bin');
  });

  it('is Python that compiles', () => {
    const compiled = spawnSync('python3', ['-c', 'import sys; compile(sys.stdin.read(), "members", "exec")'], { input: MEMBERS_PY, encoding: 'utf8' });
    expect(compiled.stderr).toBe('');
    expect(compiled.status).toBe(0);
  });
});

describe('the probe files', () => {
  const schema = JSON.parse(readFileSync(join(HERE, 'qa', 'probes.schema.json'), 'utf8')) as {
    properties: { probes: { items: { properties: Record<string, { enum?: string[] }>; required: string[] } } };
  };
  const item = schema.properties.probes.items;

  it('are described by a schema that agrees with the parser', () => {
    expect(item.properties.role.enum).toEqual([...ROLES]);
    expect(item.properties.language.enum).toEqual([...LANGUAGES]);
    expect(item.properties.expect.enum).toEqual([...EXPECTS]);
    expect(item.properties.decide.enum).toEqual([...DECISIONS]);
    expect(item.required).toEqual(['id', 'app', 'tool', 'role', 'language', 'phrase', 'expect']);
  });

  it('of the corpus parse, with every phrase written and each kind of probe present', () => {
    const dir = join(HERE, 'qa', 'probes');
    const sources = readdirSync(dir).filter((name) => name.endsWith('.json')).sort();
    expect(sources.length).toBeGreaterThan(0);
    const probes = loadedProbes(sources.map((name) => ({ source: name, text: readFileSync(join(dir, name), 'utf8') })));
    expect(probes.filter((p) => !p.phrase.trim()).map((p) => p.id)).toEqual([]);
    expect(new Set(probes.map((p) => p.expect))).toEqual(new Set(EXPECTS));
    expect(new Set(probes.map((p) => p.language))).toEqual(new Set(LANGUAGES));
  });
});
