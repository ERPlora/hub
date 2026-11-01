// Layer 2 of the assistant's QA with the real model (docs plan 2026-10-31 of erplora-next, the assistant's knowledge
// and QA, §1.5): PROBES. A probe is one NEW natural phrase a QA agent writes for one tool, as a person of one role
// would type it in one language (never one of the tool's own `asks`: it measures that the assistant generalises), and
// what that turn must do: run the read, show the write's card, refuse what the role may not do, or search the docs.
// Pure, so Vitest proves it (assistant-probes.test.ts): reading and checking the probe files (qa/probes/*.json, schema
// qa/probes.schema.json) against the catalogue `manage.py export_assistant_catalog` exports per role and language, the
// verdict of a turn, the report, the skeleton generator (`pnpm qa:probes`, run as a script) and the SaaS seed of a
// manager and an admin of `a`. qa/assistant-probes.spec.ts drives Chrome with it, only with QA_REAL_PROVIDER=1.
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { ALWAYS, type Observed } from './assistant-battery.ts';

export const ROLES = ['owner', 'admin', 'manager', 'employee'] as const;
export type Role = (typeof ROLES)[number];
export const LANGUAGES = ['en', 'es'] as const;
export type Language = (typeof LANGUAGES)[number];
/** What the turn must do: run the read, show the write's card, refuse (the role lacks the tool), search the docs. */
export const EXPECTS = ['read', 'card', 'refused', 'docs'] as const;
export type Expect = (typeof EXPECTS)[number];
/** What the person does with a card: cancel it (the default: nothing changes) or confirm it (seeded data only). */
export const DECISIONS = ['cancel', 'confirm'] as const;
export type Decision = (typeof DECISIONS)[number];

export interface Probe {
  id: string;
  app: string;
  /** The operation's name (`sale.sale.today`), as the catalogue names it. */
  tool: string;
  role: Role;
  language: Language;
  phrase: string;
  expect: Expect;
  decide?: Decision;
  notes?: string;
}

/** One tool of `export_assistant_catalog` (`live.assistant_qa.export_catalog`). */
export interface Tool {
  name: string;
  tool_name: string;
  app_label: string;
  kind: 'read' | 'write';
  permission: string;
  risk: string;
  description: string;
  asks: string[];
  input_schema?: unknown;
}
export type Catalog = Tool[];

/** How a skeleton was drawn (`pnpm qa:probes`): kept in its file, so the sample can be drawn again. */
export interface Generated {
  role: Role;
  language: Language;
  apps: string[];
  sample: number;
  all: boolean;
  seed: number;
}

export interface ProbeFile {
  generated?: Generated;
  probes: Probe[];
}

/** What the spec measured for one probe; `problems` (the probe is wrong, so no turn was asked) make it n.a. */
export interface ProbeOutcome {
  probe: Probe;
  answer: string;
  observed: Observed;
  decided: 'confirmed' | 'cancelled' | 'none';
  notices: string[];
  screenshot: string;
  problems: string[];
}

export interface ProbeVerdict {
  verdict: 'PASS' | 'FAIL' | 'N/A';
  reasons: string[];
  /** The tool the model went for: its card's write, else the first of the business it called, else the docs, else none. */
  chosen: string;
}

export interface ProbeMeta {
  run: string;
  model: string;
  fallback: string;
  service: string;
  files: string[];
}

const DOCS_SEARCH = 'base.docs.search';
const ID = /^[a-z0-9][a-z0-9._-]*$/;
const FIELDS = new Set(['id', 'app', 'tool', 'role', 'language', 'phrase', 'expect', 'decide', 'notes']);
/** How much of an answer the report shows. */
const ANSWER_CHARS = 300;

const listed = (values: readonly string[]) => values.join(', ');

/** The probes of one file; anything that is not a probe file stops the run, naming the file and the probe. */
export function parseProbeFile(text: string, source: string): Probe[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`${source}: not JSON (${(error as Error).message})`);
  }
  const probes = (parsed as { probes?: unknown } | null)?.probes;
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed) || !Array.isArray(probes)) {
    throw new Error(`${source}: a probe file is an object with a "probes" list`);
  }
  return probes.map((entry, index) => probeOf(entry, `${source}, probe ${index + 1}`));
}

function probeOf(entry: unknown, where: string): Probe {
  if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) throw new Error(`${where}: not an object`);
  const raw = entry as Record<string, unknown>;
  const fail = (what: string): never => {
    throw new Error(`${where} (${typeof raw.id === 'string' ? raw.id : '?'}): ${what}`);
  };
  for (const key of Object.keys(raw)) if (!FIELDS.has(key)) fail(`unknown field «${key}»`);
  const text = (key: string, { empty = false } = {}): string => {
    const value = raw[key];
    if (typeof value !== 'string' || (!empty && !value.trim())) fail(`${key} must be a${empty ? '' : ' non-empty'} text`);
    return value as string;
  };
  const oneOf = <T extends string>(key: string, values: readonly T[]): T => {
    const value = raw[key];
    if (!values.includes(value as T)) fail(`${key} must be one of ${listed(values)}, not «${String(value)}»`);
    return value as T;
  };
  const id = text('id');
  if (!ID.test(id)) fail('id must be lowercase letters, digits, «.», «_» or «-»');
  const probe: Probe = {
    id,
    app: text('app'),
    tool: text('tool'),
    role: oneOf('role', ROLES),
    language: oneOf('language', LANGUAGES),
    phrase: text('phrase', { empty: true }),
    expect: oneOf('expect', EXPECTS),
  };
  if (raw.decide !== undefined) {
    if (probe.expect !== 'card') fail('decide is only for a «card» probe');
    probe.decide = oneOf('decide', DECISIONS);
  }
  if (raw.notes !== undefined) probe.notes = text('notes', { empty: true });
  return probe;
}

/** Every probe of `files`, in order; an id used twice stops the run, naming both files. */
export function loadedProbes(files: { source: string; text: string }[]): Probe[] {
  const seen = new Map<string, string>();
  const probes: Probe[] = [];
  for (const { source, text } of files) {
    for (const probe of parseProbeFile(text, source)) {
      const first = seen.get(probe.id);
      if (first !== undefined) throw new Error(`probe id «${probe.id}» is in ${first} and in ${source}: ids are unique`);
      seen.set(probe.id, source);
      probes.push(probe);
    }
  }
  return probes;
}

export const catalogKey = (role: Role, language: Language): string => `${role}/${language}`;

/** The catalogues a run needs: each probe's role in its language, and the owner's (a refused tool is one of the
 *  owner's that the role lacks; the owner holds every tool of an app on). */
export function catalogsNeeded(probes: Probe[]): { role: Role; language: Language }[] {
  const keys = new Set<string>();
  for (const probe of probes) {
    keys.add(catalogKey(probe.role, probe.language));
    keys.add(catalogKey('owner', probe.language));
  }
  return [...keys].sort().map((key) => {
    const [role, language] = key.split('/') as [Role, Language];
    return { role, language };
  });
}

const normalized = (text: string): string => text.toLowerCase().replace(/\s+/g, ' ').trim();

/** Why `probe` cannot be asked as written (empty: it can), checked against the exported `catalogs`. */
export function problemsOf(probe: Probe, catalogs: Record<string, Catalog>): string[] {
  if (!probe.phrase.trim()) return ['the phrase is empty: write how a person of the role would ask'];
  const owner = catalogs[catalogKey('owner', probe.language)];
  if (!owner) return [`no catalogue of the owner in ${probe.language}`];
  const mine = catalogs[catalogKey(probe.role, probe.language)];
  if (!mine) return [`no catalogue of the ${probe.role} in ${probe.language}`];
  const tool = owner.find((row) => row.name === probe.tool);
  if (!tool) return [`no tool ${probe.tool} in the owner’s catalogue`];
  const problems: string[] = [];
  if (tool.app_label !== probe.app) problems.push(`${probe.tool} is a tool of ${tool.app_label}, not of ${probe.app}`);
  const languages = [probe.language, ...LANGUAGES.filter((language) => language !== probe.language)];
  const asks = languages.flatMap((language) => catalogs[catalogKey('owner', language)]?.find((row) => row.name === probe.tool)?.asks ?? []);
  const copied = asks.find((ask) => normalized(ask) === normalized(probe.phrase));
  if (copied !== undefined) problems.push(`the phrase is one of the asks of ${probe.tool} («${copied}»): write a new one`);
  const holds = mine.some((row) => row.name === probe.tool);
  const lacks = `the ${probe.role} does not hold ${probe.tool}: expect «refused»`;
  switch (probe.expect) {
    case 'docs':
      if (probe.tool !== DOCS_SEARCH) problems.push(`a «docs» probe is of ${DOCS_SEARCH}, not of ${probe.tool}`);
      else if (!holds) problems.push(`the ${probe.role} does not hold ${DOCS_SEARCH}`);
      break;
    case 'read':
      if (tool.kind !== 'read') problems.push(`${probe.tool} is a write: expect «card», not «read»`);
      else if (!holds) problems.push(lacks);
      break;
    case 'card':
      if (tool.kind !== 'write') problems.push(`${probe.tool} is a read: expect «read», not «card»`);
      else if (!holds) problems.push(lacks);
      break;
    case 'refused':
      if (holds) problems.push(`the ${probe.role} holds ${probe.tool}: it is not refused`);
      break;
  }
  return problems;
}

/** How an answer says it cannot do what was asked (no permission, someone else's job), per language. */
const CANNOT: Record<Language, RegExp[]> = {
  es: [
    /\bno (puedo|puedes|podemos|se puede|me es posible|es posible|tengo (permiso|acceso)|tienes (el |los )?(permiso|acceso|derecho))/,
    /\bsin (permiso|acceso)/,
    /\bsolo (lo |la |los |las )?(puede|pueden|podr[aá])\b/,
    /\bsolo (el|la|los|las|un|una|tu|su) (due[ñn]|propietari|administrador|encargad|responsable|gerente)/,
    /\bno (est[aá]s|est[aá]) (autorizad|permitid)/,
    /\b(tu|su) (rol|perfil|usuario|cuenta) no (te |le )?(permite|deja|tiene)/,
  ],
  en: [
    /\b(can't|can’t|cannot|can not|unable to|not able to|not allowed|not permitted|no permission|no access)\b/,
    /\b(don't|don’t|do not|doesn't|doesn’t|does not) (have|allow|let)\b/,
    /\bonly (the |an |a |your )?(owner|admin|administrator|manager)s?\b/,
  ],
};

/** Whether `text` says, in `language`, that it cannot do what was asked. */
export function saysCannot(text: string, language: Language): boolean {
  const said = text.toLowerCase();
  return CANNOT[language].some((pattern) => pattern.test(said));
}

/** The tool the model went for in a turn (`ProbeVerdict.chosen`): the write of its card (a read before it only looked
 *  the record up), else the first tool of the business it called, else the docs. */
export function chosenTool(seen: Observed): string {
  if (seen.cards.length) return seen.cards[0].operation;
  const business = seen.executed.find((row) => !ALWAYS.includes(row.name));
  if (business) return business.name;
  if (seen.executed.some((row) => row.name === DOCS_SEARCH)) return DOCS_SEARCH;
  return 'none';
}

/** The automatic verdict of one probe: what ran, the cards and the decision, never the wording (but the refusal's). */
export function probeVerdict(outcome: ProbeOutcome): ProbeVerdict {
  const { probe, observed: seen } = outcome;
  if (outcome.problems.length) return { verdict: 'N/A', reasons: [...outcome.problems], chosen: 'none' };
  const reasons: string[] = [];
  for (const code of seen.errors) reasons.push(`the turn ended with the error ${code}`);
  if (!outcome.answer.trim()) reasons.push('no answer');
  const ran = seen.executed.filter((row) => row.outcome === 'ok');
  const wrote = ran.filter((row) => row.kind === 'command');
  const business = ran.filter((row) => !ALWAYS.includes(row.name));
  const names = (rows: { name: string }[]) => rows.map((row) => row.name).join(', ');
  const noWrite = () => {
    if (wrote.length) reasons.push(`a write ran: ${names(wrote)}`);
    if (seen.cards.length) reasons.push(`a card was shown: ${seen.cards.map((card) => card.operation).join(', ')}`);
  };
  switch (probe.expect) {
    case 'read':
      if (!ran.some((row) => row.name === probe.tool && row.kind === 'query')) {
        reasons.push(`${probe.tool} did not run (ran: ${names(business) || 'none'})`);
      }
      noWrite();
      break;
    case 'card': {
      if (!seen.cards.some((card) => card.operation === probe.tool)) {
        reasons.push(`no card of ${probe.tool} (cards: ${seen.cards.map((card) => card.operation).join(', ') || 'none'})`);
      }
      if ((probe.decide ?? 'cancel') === 'cancel') {
        if (outcome.decided !== 'cancelled') reasons.push('the card was not cancelled');
        if (wrote.length) reasons.push(`a write ran: ${names(wrote)}`);
      } else if (outcome.decided !== 'confirmed') {
        reasons.push('the card was not confirmed');
      } else {
        if (!wrote.some((row) => row.name === probe.tool)) {
          const tries = seen.executed.filter((row) => row.name === probe.tool);
          const said = tries.map((row) => `${row.outcome}${row.code ? ` ${row.code}` : ''}`).join(', ') || 'it never ran';
          reasons.push(`${probe.tool} did not report success after its card (${said})`);
        }
        const others = wrote.filter((row) => row.name !== probe.tool);
        if (others.length) reasons.push(`another write ran: ${names(others)}`);
      }
      break;
    }
    case 'refused':
      if (business.length) reasons.push(`a tool of the business ran: ${names(business)}`);
      if (seen.cards.length) reasons.push(`a card was shown: ${seen.cards.map((card) => card.operation).join(', ')}`);
      if (!saysCannot(outcome.answer, probe.language)) reasons.push('the answer does not say it cannot');
      break;
    case 'docs':
      if (!ran.some((row) => row.name === DOCS_SEARCH)) reasons.push(`${DOCS_SEARCH} did not run`);
      else if (!seen.citations.length) reasons.push(`${DOCS_SEARCH} returned no excerpt`);
      noWrite();
      break;
  }
  return { verdict: reasons.length ? 'FAIL' : 'PASS', reasons, chosen: chosenTool(seen) };
}

/** A value for one table cell: pipes escaped, lines kept as `<br>`. */
const cell = (text: string) => text.replace(/\|/g, '\\|').replace(/\r?\n/g, '<br>');

/** The report of a run: the counts, one row per probe and the reasons of each failure and n.a. */
export function renderProbeReport(outcomes: ProbeOutcome[], meta: ProbeMeta): string {
  const judged = outcomes.map((outcome) => ({ outcome, verdict: probeVerdict(outcome) }));
  const count = (verdict: ProbeVerdict['verdict']) => judged.filter((row) => row.verdict.verdict === verdict).length;
  const lines = [
    '# Hub assistant QA — layer 2 probes (real model)',
    '',
    `- Run: ${meta.run}`,
    `- Answering model: ${meta.model || 'unknown'} · fallback: ${meta.fallback || 'none'} · embeddings: ${meta.service || 'unknown'}`,
    `- Probe files: ${meta.files.join(', ') || 'none'}`,
    `- Verdicts: PASS ${count('PASS')} · FAIL ${count('FAIL')} · N/A ${count('N/A')}`,
    '',
    '| Probe | Role | Lang | Expect | Verdict | Tool chosen | Phrase | Answer (first 300 chars) |',
    '|---|---|---|---|---|---|---|---|',
    ...judged.map(({ outcome, verdict }) => {
      const { probe } = outcome;
      const expected = probe.decide === 'confirm' ? `${probe.expect} (confirm)` : probe.expect;
      return `| ${probe.id} | ${probe.role} | ${probe.language} | ${expected} | ${verdict.verdict} | ${verdict.chosen} | ${cell(probe.phrase)} | ${cell(outcome.answer.slice(0, ANSWER_CHARS))} |`;
    }),
  ];
  const wrong = judged.filter((row) => row.verdict.verdict !== 'PASS');
  if (wrong.length) {
    lines.push('', '## Failures and n.a.', '');
    for (const { outcome, verdict } of wrong) {
      lines.push(`- **${outcome.probe.id}** (${verdict.verdict}): ${verdict.reasons.join('; ')} — screenshot ${outcome.screenshot || 'none'}`);
    }
  }
  return `${lines.join('\n')}\n`;
}

// ── The skeleton generator (`pnpm qa:probes`) ──

/** A small seeded generator (mulberry32): the same seed draws the same sample. */
function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffled<T>(items: T[], next: () => number): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** `count` of `tools`, reads and writes taken in turn (which first, by the draw), so a sample of two has one of each. */
function mixed(tools: Tool[], count: number, next: () => number): Tool[] {
  const byName = (a: Tool, b: Tool) => a.name.localeCompare(b.name);
  const piles = [
    shuffled(tools.filter((row) => row.kind === 'read').sort(byName), next),
    shuffled(tools.filter((row) => row.kind === 'write').sort(byName), next),
  ];
  if (next() < 0.5) piles.reverse();
  const out: Tool[] = [];
  for (let turn = 0; out.length < count && (piles[0].length || piles[1].length); turn++) {
    const pile = piles[turn % 2].length ? piles[turn % 2] : piles[(turn + 1) % 2];
    out.push(pile.shift() as Tool);
  }
  return out;
}

export interface SkeletonOptions {
  role: Role;
  language: Language;
  /** Tools per app (each of the role's, and as many it lacks), unless `all`. */
  sample: number;
  all: boolean;
  seed: number;
  /** How many «docs» probes. */
  docs: number;
}

const ORDER: Record<Expect, number> = { docs: 0, read: 1, card: 2, refused: 3 };

/**
 * A probe file to fill: per app of the catalogues, `sample` tools of the role (reads and writes mixed; `all`: every
 * one) and as many of the owner's the role lacks (expected refused), plus `docs` probes of the documentation, each
 * with its phrase EMPTY for the QA agent to write. What to expect comes from the tool: a read, a write's card, or a
 * refusal. The tools every turn is offered (`ALWAYS`) are not sampled: the «docs» probes ask the documentation.
 */
export function skeleton(roleCatalog: Catalog, ownerCatalog: Catalog, options: SkeletonOptions): ProbeFile {
  const next = random(options.seed);
  const held = new Set(roleCatalog.map((row) => row.name));
  const describe = new Map([...roleCatalog, ...ownerCatalog].map((row) => [row.name, row.description]));
  const apps = [...new Set([...roleCatalog, ...ownerCatalog].map((row) => row.app_label))].sort();
  const ids = new Set<string>();
  const probes: Probe[] = [];
  const add = (tool: string, app: string, expect: Expect) => {
    const base = `${options.role}.${options.language}.${tool}`;
    let id = base;
    for (let n = 2; ids.has(id); n++) id = `${base}-${n}`;
    ids.add(id);
    probes.push({ id, app, tool, role: options.role, language: options.language, phrase: '', expect, notes: describe.get(tool) ?? '' });
  };
  if (held.has(DOCS_SEARCH)) for (let n = 0; n < options.docs; n++) add(DOCS_SEARCH, 'base', 'docs');
  const offered = (row: Tool) => !ALWAYS.includes(row.name);
  for (const app of apps) {
    const mine = roleCatalog.filter((row) => row.app_label === app && offered(row));
    const lacked = ownerCatalog.filter((row) => row.app_label === app && offered(row) && !held.has(row.name));
    const taken = options.all ? mine : mixed(mine, options.sample, next);
    for (const row of taken) add(row.name, app, row.kind === 'read' ? 'read' : 'card');
    const refused = options.all ? lacked : shuffled([...lacked].sort((a, b) => a.name.localeCompare(b.name)), next).slice(0, options.sample);
    for (const row of refused) add(row.name, app, 'refused');
  }
  probes.sort((a, b) => a.app.localeCompare(b.app) || ORDER[a.expect] - ORDER[b.expect] || a.tool.localeCompare(b.tool));
  const generated: Generated = {
    role: options.role,
    language: options.language,
    apps,
    sample: options.sample,
    all: options.all,
    seed: options.seed,
  };
  return { generated, probes };
}

const USAGE =
  'Usage: pnpm qa:probes --role <owner|admin|manager|employee> --language <en|es> [--apps a,b] [--sample N | --all] ' +
  '[--seed N] [--docs N] [--out file.json]';

export interface CliDeps {
  /** `manage.py export_assistant_catalog` of the role in the language (every app, or `apps`). */
  exportCatalog: (role: Role, language: Language, apps: string[]) => Catalog;
  write: (path: string, text: string) => void;
  print: (line: string) => void;
  fail: (line: string) => void;
  now: () => number;
}

/** `pnpm qa:probes …`: the exit code (0 written, 1 the export failed, 2 a wrong call). */
export function runCli(args: string[], deps: CliDeps): number {
  const values: Record<string, string> = {};
  let all = false;
  const wrong = (what: string) => {
    deps.fail(`qa:probes: ${what}. ${USAGE}`);
    return 2;
  };
  for (let i = 0; i < args.length; i++) {
    const flag = args[i];
    if (flag === '--all') {
      all = true;
    } else if (['--role', '--language', '--apps', '--sample', '--seed', '--docs', '--out'].includes(flag) && i + 1 < args.length) {
      values[flag.slice(2)] = args[++i];
    } else {
      return wrong(`unknown argument ${flag}`);
    }
  }
  const role = values.role as Role;
  const language = values.language as Language;
  if (!ROLES.includes(role)) return wrong(`--role must be one of ${listed(ROLES)}`);
  if (!LANGUAGES.includes(language)) return wrong(`--language must be one of ${listed(LANGUAGES)}`);
  const count = (name: string, fallback: number, least: number): number | null => {
    if (values[name] === undefined) return fallback;
    const value = Number(values[name]);
    return Number.isInteger(value) && value >= least ? value : null;
  };
  const sample = count('sample', 2, 1);
  const seed = count('seed', deps.now(), 0);
  const docs = count('docs', 1, 0);
  if (sample === null) return wrong('--sample must be a whole number from 1');
  if (seed === null) return wrong('--seed must be a whole number from 0');
  if (docs === null) return wrong('--docs must be a whole number from 0');
  const apps = (values.apps ?? '').split(',').map((app) => app.trim()).filter(Boolean);
  try {
    const mine = deps.exportCatalog(role, language, apps);
    const owner = role === 'owner' ? mine : deps.exportCatalog('owner', language, apps);
    const made = skeleton(mine, owner, { role, language, sample, all, seed, docs });
    const out = values.out || join('tests', 'e2e', '.artifacts', 'qa', `probes-${role}-${language}-${seed}.json`);
    deps.write(out, `${JSON.stringify(made, null, 2)}\n`);
    const of = (expect: Expect) => made.probes.filter((probe) => probe.expect === expect).length;
    deps.print(
      `qa:probes: ${out}: ${made.probes.length} probes (${of('read')} read, ${of('card')} card, ${of('refused')} refused, ` +
        `${of('docs')} docs) for the ${role} in ${language}, seed ${seed}; write each phrase (empty now) before a run`,
    );
    return 0;
  } catch (error) {
    deps.fail(`qa:probes: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  }
}

// ── The members of `a` the SaaS's demo seed lacks ──

interface Credentials {
  email: string;
  password: string;
}

/** A manager and an admin of `a` (development only; `demo_seed` gives the owner and the employee). */
export const MEMBERS: Record<'manager' | 'admin', Credentials> = {
  manager: { email: 'qa-manager@example.com', password: 'manager' },
  admin: { email: 'qa-admin@example.com', password: 'admin' },
};

/**
 * The SaaS side (`manage.py shell -c` in the stack's SaaS, DEBUG only): the two accounts as `demo_seed` makes its
 * own, members of `a` with their roles through `seed_demo_business`, which only adds what is missing and mirrors
 * the access the jump to the Hub reads.
 */
export const MEMBERS_PY = `
import json
from django.conf import settings
from accounts import services as account_services
from hubs import services
from hubs.models import HubMember

if not settings.DEBUG:
    raise SystemExit("the QA members' seed only runs with DEBUG=True")
manager = account_services.seed_demo_customer("${MEMBERS.manager.email}", "${MEMBERS.manager.password}")
admin = account_services.seed_demo_customer("${MEMBERS.admin.email}", "${MEMBERS.admin.password}")
services.seed_demo_business("a", {manager: HubMember.Role.MANAGER, admin: HubMember.Role.ADMIN})
print(json.dumps({"manager": manager.email, "admin": admin.email}))
`;

/** How the members' seed runs from the stack's SaaS checkout, on `saasDatabase`. */
export function membersCommand(
  env: Record<string, string | undefined>,
  saasDatabase: string,
): { file: string; args: string[]; env: Record<string, string> } {
  const base = Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));
  return { file: 'uv', args: ['run', 'python', 'manage.py', 'shell', '-c', MEMBERS_PY], env: { ...base, DB_NAME: saasDatabase } };
}

/** The Hub's checkout: where `manage.py` runs. */
export const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** `manage.py export_assistant_catalog` of `role` in `language` (every app, or `apps`), parsed; its error, else. */
export function exportCatalog(role: Role, language: Language, apps: string[] = [], env: NodeJS.ProcessEnv = process.env): Catalog {
  const args = ['run', 'python', 'manage.py', 'export_assistant_catalog', '--role', role, '--language', language];
  if (apps.length) args.push('--apps', apps.join(','));
  try {
    const out = execFileSync('uv', args, { cwd: HUB_DIR, env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 256 * 1024 * 1024 });
    return JSON.parse(out) as Catalog;
  } catch (error) {
    const failed = error as { stderr?: string; message: string };
    const said = (failed.stderr ?? '').trim().split('\n').at(-1) || failed.message;
    throw new Error(`export_assistant_catalog --role ${role} --language ${language}: ${said}`);
  }
}

// Run as a script (`pnpm qa:probes`), not when a test or the spec imports it.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = runCli(process.argv.slice(2), {
    exportCatalog: (role, language, apps) => exportCatalog(role, language, apps),
    write: (path, text) => {
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, text);
    },
    print: (line) => console.log(line),
    fail: (line) => console.error(line),
    now: () => Math.floor(Date.now() / 1000),
  });
}
