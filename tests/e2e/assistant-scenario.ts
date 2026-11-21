// A scenario of the assistant's QA (qa/scenarios/*.json): a whole job a business owner asks the assistant for in plain
// words, in one conversation. It says the business it starts from (a seed and a setup made by the Hub's tools, with no
// model), who the owner is and what it says up front or only when asked, the files it attaches, the database state the
// job must end in, the changes that must not happen, the facts the assistant must ask for instead of inventing, and the
// calls a perfect assistant would make (its golden path). Pure, so Vitest proves it (assistant-scenario.test.ts).

export const VERTICALS = ['restaurant', 'hair_salon'] as const;
export type Vertical = (typeof VERTICALS)[number];

/** How the owner says the job: by halves, so the assistant must ask what to do before writing, or whole. */
export const SAID = ['half', 'whole'] as const;
export type Said = (typeof SAID)[number];

/** A tool call the Hub runs as the owner: a setup step or a step of the golden path. An argument may be
 *  `{"$ref": "<step id>", "where": {...}, "take": "id"}`: a value of an earlier step's result (assistant-golden.ts). */
export interface ToolStep {
  id?: string;
  tool: string;
  arguments: Record<string, unknown>;
}

/** One SQL check on the business's database: its single value equals `equals`, or what it was before the job. */
export interface Check {
  says: string;
  sql: string;
  equals?: string;
  unchanged?: boolean;
}

export interface DeliveryNote {
  supplier: string;
  number: string;
  date: string;
  lines: { product: string; quantity: string; unitCost: string }[];
}

export type Attachment =
  | { kind: 'xlsx'; name: string; sheet: string; rows: (string | number | null)[][] }
  | { kind: 'pdf' | 'photo'; name: string; note: DeliveryNote };

/** A call that would use a fact: its tool, the `path` into its arguments, and, when it is about one record, the
 *  arguments that name it (`{"name": "pulpo"}`: the call's `name` contains «pulpo»). */
export interface Use {
  tool: string;
  path: string;
  where?: Record<string, string>;
}

/** A fact the owner only says when asked: how its answer reveals it, and the calls that would use it. `resolvers`:
 *  reads that may find it instead of asking (a tax category from its list). */
export interface MustAsk {
  id: string;
  fact: string;
  reveals: string[];
  uses: Use[];
  resolvers?: string[];
}

/** The card of a write whose arguments contain `match` must show `expect`. */
export interface CardCheck {
  tool: string;
  match: Record<string, string>;
  expect: Record<string, string | number>;
}

export interface Owner {
  persona: string;
  goal: string;
  upFront: string[];
  ifAsked: string[];
}

export interface Scenario {
  id: string;
  title: string;
  vertical: Vertical;
  /** Absent: the scenario is not scored on asking before acting. */
  said?: Said;
  /** The seed of the vertical loaded into the business (`base.blueprint.import`): `restaurant.es`. */
  seed: string;
  language: 'es' | 'en';
  setup: ToolStep[];
  owner: Owner;
  attachments: Attachment[];
  opening: string;
  /** The tools the opening message (with its files) must be offered; without them it is not runnable. */
  offered: string[];
  /** The tools whose writes the job wants; any other write is unwanted. */
  writes: string[];
  cards: CardCheck[];
  expect: Check[];
  forbidden: Check[];
  mustAsk: MustAsk[];
  /** The owner's messages at most, the opening included. */
  maxTurns: number;
  golden: ToolStep[];
}

const ID = /^s\d{2}-[a-z0-9-]+$/;
const TOOL = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;
const SEED = /^[a-z_]+\.(es|en)$/;

type Raw = Record<string, unknown>;

const isObject = (value: unknown): value is Raw => typeof value === 'object' && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim() !== '';

class Fields {
  private readonly raw: Raw;
  private readonly where: string;
  private readonly prefix: string;

  constructor(raw: Raw, where: string, prefix = '') {
    this.raw = raw;
    this.where = where;
    this.prefix = prefix;
  }

  fail(field: string, why: string): never {
    throw new Error(`${this.where}: ${this.prefix}${field}${why ? ` ${why}` : ''}`);
  }

  text(field: string): string {
    const value = this.raw[field];
    return isText(value) ? value : this.fail(field, 'is a text');
  }

  texts(field: string, atLeast = 0): string[] {
    const value = this.raw[field];
    if (!Array.isArray(value) || value.length < atLeast || !value.every(isText)) this.fail(field, `is a list of texts${atLeast ? ', not empty' : ''}`);
    return value as string[];
  }

  list(field: string): unknown[] {
    const value = this.raw[field] ?? [];
    return Array.isArray(value) ? value : this.fail(field, 'is a list');
  }

  object(field: string): Raw {
    const value = this.raw[field];
    return isObject(value) ? value : this.fail(field, 'is an object');
  }

  oneOf<T extends string>(field: string, options: readonly T[]): T {
    const value = this.raw[field];
    return options.includes(value as T) ? (value as T) : this.fail(field, `is one of ${options.join(', ')}`);
  }
}

function step(entry: unknown, where: string): ToolStep {
  if (!isObject(entry) || typeof entry.tool !== 'string' || !TOOL.test(entry.tool)) throw new Error(`${where}: names its tool as <app>.<entity>.<action>`);
  if (!isObject(entry.arguments)) throw new Error(`${where}: its arguments are an object`);
  if (entry.id !== undefined && !isText(entry.id)) throw new Error(`${where}: its id is a text`);
  return { ...(entry.id ? { id: entry.id as string } : {}), tool: entry.tool, arguments: entry.arguments };
}

function check(entry: unknown, where: string): Check {
  const fields = new Fields(isObject(entry) ? entry : {}, where);
  const says = isObject(entry) && isText(entry.says) ? entry.says : fields.fail('says', 'what the check means, in words');
  const sql = fields.text('sql');
  if (/["$`]/.test(sql)) fields.fail('sql', 'has no double quotes, dollars or backticks (the shell would change them)');
  const equals = (entry as Raw).equals;
  const unchanged = (entry as Raw).unchanged === true;
  if ((typeof equals === 'string') === unchanged) fields.fail('equals or unchanged', 'one of the two');
  return unchanged ? { says, sql, unchanged } : { says, sql, equals: equals as string };
}

function note(raw: unknown, where: string): DeliveryNote {
  const fields = new Fields(isObject(raw) ? raw : {}, where);
  const lines = isObject(raw) && Array.isArray(raw.lines) ? raw.lines : [];
  const read = lines.map((line) => (isObject(line) && isText(line.product) && isText(line.quantity) && isText(line.unitCost) ? line : null));
  if (!read.length || read.includes(null)) fields.fail('note', 'has a supplier, number, date and lines of product, quantity and unitCost');
  return { supplier: fields.text('supplier'), number: fields.text('number'), date: fields.text('date'), lines: read as unknown as DeliveryNote['lines'] };
}

const isCell = (cell: unknown): boolean => cell === null || typeof cell === 'string' || typeof cell === 'number';

function attachment(entry: unknown, where: string): Attachment {
  const fields = new Fields(isObject(entry) ? entry : {}, where);
  const kind = fields.oneOf('kind', ['xlsx', 'pdf', 'photo'] as const);
  const name = fields.text('name');
  if (kind !== 'xlsx') return { kind, name, note: note((entry as Raw).note, `${where}: note`) };
  const rows = (entry as Raw).rows;
  if (!Array.isArray(rows) || !rows.length || !rows.every((row) => Array.isArray(row) && row.every(isCell))) fields.fail('rows', 'are rows of texts, numbers or nulls');
  return { kind, name, sheet: fields.text('sheet'), rows: rows as (string | number | null)[][] };
}

function mustAsk(entry: unknown, where: string): MustAsk {
  const fields = new Fields(isObject(entry) ? entry : {}, where);
  const uses = fields.list('uses');
  const named = (where: unknown) => where === undefined || (isObject(where) && Object.values(where).every(isText));
  const usable = uses.every((use) => isObject(use) && typeof use.tool === 'string' && TOOL.test(use.tool) && isText(use.path) && named(use.where));
  if (!uses.length || !usable) fields.fail('uses', 'is a list of {tool, path}, not empty');
  const resolvers = fields.list('resolvers');
  if (!resolvers.every((tool) => typeof tool === 'string' && TOOL.test(tool))) fields.fail('resolvers', 'is a list of tools');
  return {
    id: fields.text('id'),
    fact: fields.text('fact'),
    reveals: fields.texts('reveals', 1),
    uses: uses as Use[],
    ...(resolvers.length ? { resolvers: resolvers as string[] } : {}),
  };
}

function cardCheck(entry: unknown, where: string): CardCheck {
  const fields = new Fields(isObject(entry) ? entry : {}, where);
  const tool = fields.text('tool');
  if (!TOOL.test(tool)) fields.fail('tool', 'is <app>.<entity>.<action>');
  const expected = fields.object('expect');
  if (!Object.keys(expected).length) fields.fail('expect', 'names at least one value');
  return { tool, match: fields.object('match') as Record<string, string>, expect: expected as Record<string, string | number> };
}

function owner(raw: unknown, where: string): Owner {
  const fields = new Fields(isObject(raw) ? raw : {}, where, 'owner.');
  return { persona: fields.text('persona'), goal: fields.text('goal'), upFront: fields.texts('upFront', 1), ifAsked: fields.texts('ifAsked') };
}

const plain = (text: string): string => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

function saidUpFront(scenario: Scenario, source: string): void {
  const said = plain([scenario.opening, ...scenario.owner.upFront].join(' '));
  for (const fact of scenario.mustAsk) {
    const told = fact.reveals.find((text) => said.includes(plain(text)));
    if (told) throw new Error(`${source}: mustAsk ${fact.id}: the owner says «${told}» up front, so it cannot be asked for`);
  }
}

const each = <T>(fields: Fields, field: string, read: (entry: unknown, where: string) => T, where: string): T[] =>
  fields.list(field).map((entry, index) => read(entry, `${where}: ${field} ${index + 1}`));

/** A scenario file; anything a run could not use stops it, naming the file and the field. */
export function parseScenario(text: string, source: string): Scenario {
  const raw = JSON.parse(text) as unknown;
  const fields = new Fields(isObject(raw) ? raw : {}, source);
  const id = fields.text('id');
  if (!ID.test(id)) fields.fail('id', 'is s<NN>-<words>');
  const seed = fields.text('seed');
  if (!SEED.test(seed)) fields.fail('seed', 'is <vertical>.<language>');
  const maxTurns = (raw as Raw).maxTurns;
  if (!Number.isInteger(maxTurns) || (maxTurns as number) < 1 || (maxTurns as number) > 30) fields.fail('maxTurns', 'is 1 to 30');
  const writes = fields.texts('writes');
  const offered = fields.texts('offered');
  for (const [field, tools] of [['writes', writes], ['offered', offered]] as const) if (!tools.every((tool) => TOOL.test(tool))) fields.fail(field, 'is a list of tools');
  const scenario: Scenario = {
    id,
    title: fields.text('title'),
    vertical: fields.oneOf('vertical', VERTICALS),
    ...((raw as Raw).said === undefined ? {} : { said: fields.oneOf('said', SAID) }),
    seed,
    language: fields.oneOf('language', ['es', 'en'] as const),
    setup: each(fields, 'setup', step, source),
    owner: owner((raw as Raw).owner, source),
    attachments: each(fields, 'attachments', attachment, source),
    opening: fields.text('opening'),
    offered,
    writes,
    cards: each(fields, 'cards', cardCheck, source),
    expect: each(fields, 'expect', check, source),
    forbidden: each(fields, 'forbidden', check, source),
    mustAsk: each(fields, 'mustAsk', mustAsk, source),
    maxTurns: maxTurns as number,
    golden: each(fields, 'golden', step, source),
  };
  if (!scenario.expect.length) fields.fail('expect:', 'at least one check');
  saidUpFront(scenario, source);
  return scenario;
}

/** Every scenario of `files`; an id in two files stops the run. */
export function loadedScenarios(files: { source: string; text: string }[]): Scenario[] {
  const seen = new Map<string, string>();
  return files.map(({ source, text }) => {
    const scenario = parseScenario(text, source);
    const earlier = seen.get(scenario.id);
    if (earlier) throw new Error(`${source}: id ${scenario.id} is also in ${earlier}`);
    seen.set(scenario.id, source);
    return scenario;
  });
}
