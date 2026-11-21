// @vitest-environment node
// The format of a scenario of the assistant's QA (qa/scenarios/*.json): a whole job a business owner asks for in plain
// words, the business it starts from, what the owner knows, the files it attaches, the database state the job must end
// in and the scripted calls a perfect assistant would make.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { loadedScenarios, parseScenario, type Scenario } from './assistant-scenario';

const minimal = (): Record<string, unknown> => ({
  id: 's99-example',
  title: 'Example',
  vertical: 'restaurant',
  seed: 'restaurant.es',
  language: 'es',
  setup: [],
  owner: { persona: 'Ana, dueña de un bar', goal: 'Añadir un producto', upFront: ['Se llama Tarta'], ifAsked: ['Cuesta 5,50 €'] },
  attachments: [],
  opening: 'Añade la tarta',
  writes: ['inventory.product.create'],
  cards: [],
  expect: [{ says: 'the cake exists', sql: "select count(*) from inventory_product where name = 'Tarta'", equals: '1' }],
  forbidden: [{ says: 'nothing deleted', sql: 'select count(*) from inventory_product where is_deleted', unchanged: true }],
  mustAsk: [{ id: 'price', fact: 'its price', reveals: ['5,50'], uses: [{ tool: 'inventory.product.create', path: 'price' }] }],
  maxTurns: 6,
  golden: [{ tool: 'inventory.product.create', arguments: { name: 'Tarta', sku: 'TAR-01', price: 550, tax_category_key: 'restaurant.food' } }],
});

const parsed = (changes: Record<string, unknown>): Scenario => parseScenario(JSON.stringify({ ...minimal(), ...changes }), 'qa/scenarios/x.json');

describe('parseScenario', () => {
  it('reads a whole scenario as it is written', () => {
    const scenario = parsed({});
    expect(scenario.id).toBe('s99-example');
    expect(scenario.owner.ifAsked).toEqual(['Cuesta 5,50 €']);
    expect(scenario.mustAsk[0].uses).toEqual([{ tool: 'inventory.product.create', path: 'price' }]);
    expect(scenario.golden[0].tool).toBe('inventory.product.create');
  });

  it('refuses what a run could not use, naming the file and the field', () => {
    expect(() => parsed({ id: 'Bad id' })).toThrow(/qa\/scenarios\/x.json: id/);
    expect(() => parsed({ vertical: 'shop' })).toThrow(/vertical/);
    expect(() => parsed({ language: 'fr' })).toThrow(/language/);
    expect(() => parsed({ opening: ' ' })).toThrow(/opening/);
    expect(() => parsed({ maxTurns: 0 })).toThrow(/maxTurns/);
    expect(() => parsed({ owner: { persona: 'x', goal: 'y', upFront: 'z', ifAsked: [] } })).toThrow(/owner.upFront/);
    expect(() => parsed({ writes: ['product'] })).toThrow(/writes/);
    expect(() => parsed({ golden: [{ tool: 'a.b', arguments: {} }] })).toThrow(/golden 1/);
    expect(() => parsed({ setup: [{ tool: 'a.b.c', arguments: [] }] })).toThrow(/setup 1/);
  });

  it('wants each check to compare its SQL with a value or with itself before the job, one of the two', () => {
    expect(() => parsed({ expect: [{ says: 'x', sql: 'select 1' }] })).toThrow(/expect 1: equals or unchanged/);
    expect(() => parsed({ expect: [{ says: 'x', sql: 'select 1', equals: '1', unchanged: true }] })).toThrow(/expect 1: equals or unchanged/);
    expect(() => parsed({ forbidden: [{ says: '', sql: 'select 1', equals: '1' }] })).toThrow(/forbidden 1: says/);
    expect(() => parsed({ expect: [] })).toThrow(/expect: at least one check/);
  });

  it('refuses SQL the shell would change on its way to psql: double quotes, dollars and backticks', () => {
    expect(() => parsed({ expect: [{ says: 'x', sql: 'select "order" from inventory_category', equals: '1' }] })).toThrow(/expect 1: sql/);
    expect(() => parsed({ forbidden: [{ says: 'x', sql: 'select $1', unchanged: true }] })).toThrow(/forbidden 1: sql/);
  });

  it('refuses a fact to ask for that the owner already says up front or in the opening', () => {
    expect(() => parsed({ opening: 'Añade la tarta a 5,50' })).toThrow(/mustAsk price: the owner says «5,50» up front/);
    expect(() => parsed({ owner: { persona: 'p', goal: 'g', upFront: ['cuesta 5,50'], ifAsked: [] } })).toThrow(/mustAsk price/);
  });

  it('wants a fact to ask for to name how the owner reveals it and the calls that would use it', () => {
    expect(() => parsed({ mustAsk: [{ id: 'p', fact: 'x', reveals: [], uses: [{ tool: 'a.b.c', path: 'price' }] }] })).toThrow(/mustAsk 1: reveals/);
    expect(() => parsed({ mustAsk: [{ id: 'p', fact: 'x', reveals: ['1'], uses: [] }] })).toThrow(/mustAsk 1: uses/);
    expect(() => parsed({ mustAsk: [{ id: 'p', fact: 'x', reveals: ['1'], uses: [{ tool: 'a.b.c', path: '' }] }] })).toThrow(/mustAsk 1: uses/);
    expect(() => parsed({ mustAsk: [{ id: 'p', fact: 'x', reveals: ['1'], uses: [{ tool: 'a.b.c', path: 'price', where: 'pulpo' }] }] })).toThrow(/mustAsk 1: uses/);
    const where = parsed({ mustAsk: [{ id: 'p', fact: 'x', reveals: ['1'], uses: [{ tool: 'a.b.c', path: 'price', where: { name: 'pulpo' } }] }] });
    expect(where.mustAsk[0].uses[0].where).toEqual({ name: 'pulpo' });
  });

  it('reads the attachments a fixture makes: a spreadsheet, or a delivery note as a PDF or a photo', () => {
    const note = { supplier: 'Bebidas Sur', number: 'A-1', date: '{today}', lines: [{ product: 'Agua', quantity: '24', unitCost: '0,40' }] };
    const scenario = parsed({ attachments: [{ kind: 'xlsx', name: 'carta.xlsx', sheet: 'Carta', rows: [['Producto', 'Precio'], ['Tarta', 5.5], ['Pan', null]] }, { kind: 'photo', name: 'albaran.jpg', note }] });
    expect(scenario.attachments.map((file) => file.kind)).toEqual(['xlsx', 'photo']);
    expect(() => parsed({ attachments: [{ kind: 'docx', name: 'x.docx' }] })).toThrow(/attachments 1: kind/);
    expect(() => parsed({ attachments: [{ kind: 'pdf', name: 'a.pdf', note: { ...note, lines: [] } }] })).toThrow(/attachments 1: note/);
    expect(() => parsed({ attachments: [{ kind: 'xlsx', name: 'a.xlsx', sheet: 'S', rows: [[{}]] }] })).toThrow(/attachments 1: rows/);
  });

  it('reads whether the owner says the job by halves or whole, and leaves it unsaid when the scenario does not say', () => {
    expect(parsed({ said: 'half' }).said).toBe('half');
    expect(parsed({ said: 'whole' }).said).toBe('whole');
    expect(parsed({}).said).toBeUndefined();
    expect(() => parsed({ said: 'unclear' })).toThrow(/qa\/scenarios\/x.json: said is one of half, whole/);
  });

  it('reads a card check: which card it is and the values it must show', () => {
    const scenario = parsed({ cards: [{ tool: 'inventory.product.create', match: { name: 'tarta' }, expect: { price: 550 } }] });
    expect(scenario.cards).toEqual([{ tool: 'inventory.product.create', match: { name: 'tarta' }, expect: { price: 550 } }]);
    expect(() => parsed({ cards: [{ tool: 'inventory.product.create', match: {}, expect: {} }] })).toThrow(/cards 1: expect/);
  });
});

describe('loadedScenarios', () => {
  it('refuses two scenarios with the same id', () => {
    const text = JSON.stringify(minimal());
    expect(() => loadedScenarios([{ source: 'a.json', text }, { source: 'b.json', text }])).toThrow(/b.json: id s99-example is also in a.json/);
  });

  it('reads every scenario of the corpus', () => {
    const scenarios = corpus();
    expect(scenarios.length).toBe(22);
    expect(new Set(scenarios.map((scenario) => scenario.vertical))).toEqual(new Set(['restaurant', 'hair_salon']));
    expect(scenarios.some((scenario) => scenario.language === 'en')).toBe(true);
  });
});

function corpus(): Scenario[] {
  const folder = join(dirname(fileURLToPath(import.meta.url)), 'qa', 'scenarios');
  const files = readdirSync(folder).filter((name) => name.endsWith('.json'));
  return loadedScenarios(files.map((name) => ({ source: name, text: readFileSync(join(folder, name), 'utf8') })));
}

/** What makes two scenarios the same job: the business it starts from, what the owner wants and how it is checked. */
const job = (scenario: Scenario) => {
  const { vertical, seed, language, setup, writes, expect: checks, forbidden, golden, owner } = scenario;
  return { vertical, seed, language, setup, writes, checks, forbidden, golden, persona: owner.persona, goal: owner.goal };
};

describe('the jobs the owner says by halves', () => {
  const scenarios = corpus();
  const half = scenarios.filter((scenario) => scenario.said === 'half');
  const whole = scenarios.filter((scenario) => scenario.said === 'whole');

  it('are six, three of a restaurant and three of a hair salon, one of them in English', () => {
    expect(half.map((scenario) => scenario.vertical).sort()).toEqual(['hair_salon', 'hair_salon', 'hair_salon', 'restaurant', 'restaurant', 'restaurant']);
    expect(half.filter((scenario) => scenario.language === 'en')).toHaveLength(1);
  });

  it('each have their control said whole: the same job, with the same checks and golden path, under the same name', () => {
    expect(whole).toHaveLength(half.length);
    for (const scenario of half) {
      const name = scenario.id.replace(/^s\d+-/, '').replace(/-half$/, '');
      const control = whole.find((other) => other.id.replace(/^s\d+-/, '') === `${name}-whole`);
      expect(control, `${scenario.id} has no control said whole`).toBeDefined();
      expect(job(control as Scenario), `${control?.id} is not the job of ${scenario.id}`).toEqual(job(scenario));
      expect(control?.opening, `${control?.id} says the job in other words than ${scenario.id}`).not.toBe(scenario.opening);
    }
  });
});
