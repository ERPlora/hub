// The records a sampled run of the probes needs before its first probe. Many probes name a record of `a` («Comedor QA»,
// «Fichaje QA», «QA-WEB-1») that, on a fresh stack, only earlier probes or an earlier run would have made; a sample would
// then fail on «not found» whatever the model. `qa/setup.json` makes them once per run, by the Hub's own tools with
// fixed data and as `a`'s owner, with no model in the loop, so every model starts from the same business. A name counts
// as made only when its step ran and its result names it. A probe that names a record the setup does not make (or
// would create one the setup already made) is left out of the score by `missingFor`, the same for every model.
// Pure, so Vitest proves it (assistant-setup.test.ts).
import type { Probe } from './assistant-probes.ts';

export interface SetupStep {
  /** The operation (`table.zone.create`), run as a confirmed tool call. */
  tool: string;
  arguments: Record<string, unknown>;
  /** The names of the records it makes, as the probes name them. */
  provides: string[];
}

/** What the Hub's tool runner answered one step (`live.assistant.run_tool`). */
export interface StepResult {
  outcome: string;
  code: string;
  content: string;
}

export interface SetupRun {
  /** The names made, by the `<app>.<entity>` of the step that made them. */
  provided: Record<string, string[]>;
  failed: { step: number; tool: string; why: string }[];
}

const TOOL = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;
/** The actions that make a new record: what their phrase names may be the new record itself. */
const CREATES = new Set(['create', 'bulk_create', 'place', 'register', 'open', 'add', 'issue']);

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);

function stepOf(entry: unknown, where: string): SetupStep {
  if (!isObject(entry) || typeof entry.tool !== 'string' || !TOOL.test(entry.tool)) throw new Error(`${where}: a step names its tool as <app>.<entity>.<action>`);
  if (!isObject(entry.arguments)) throw new Error(`${where}: its arguments are an object`);
  const provides = entry.provides;
  if (!Array.isArray(provides) || provides.some((name) => typeof name !== 'string' || !name.trim())) throw new Error(`${where}: provides is a list of names`);
  return { tool: entry.tool, arguments: entry.arguments, provides: provides as string[] };
}

/** The steps of a setup file; anything else stops the run, naming the step. */
export function parseSetup(text: string, source: string): SetupStep[] {
  const parsed = JSON.parse(text) as unknown;
  if (!isObject(parsed) || !Array.isArray(parsed.steps)) throw new Error(`${source}: a setup is {"steps": […]}`);
  return parsed.steps.map((entry, index) => stepOf(entry, `${source}: step ${index + 1}`));
}

/** The day in Madrid, where the business is, as YYYY-MM-DD. */
export const madridToday = (now: Date): string =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);

function shifted(today: string, days: number): string {
  const day = new Date(`${today}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}

function dated(value: unknown, today: string): unknown {
  if (value === '{year}') return Number(today.slice(0, 4));
  if (typeof value === 'string') return value.replace(/\{today([+-]\d+)?\}/g, (_, days?: string) => shifted(today, Number(days ?? 0)));
  if (Array.isArray(value)) return value.map((item) => dated(item, today));
  if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, dated(item, today)]));
  return value;
}

/** The steps with `{today}`, `{today+N}`, `{today-N}` and `{year}` written as the day of the run. */
export function withDates(steps: SetupStep[], today: string): SetupStep[] {
  return steps.map((step) => ({ ...step, arguments: dated(step.arguments, today) as Record<string, unknown> }));
}

const entityOf = (tool: string): string => tool.split('.').slice(0, 2).join('.');

/** What the setup made: a step's names count only when it ran and its result names each of them. */
export function settled(steps: SetupStep[], results: StepResult[]): SetupRun {
  if (results.length !== steps.length) throw new Error(`the setup answered ${steps.length} steps, ${results.length} results`);
  const run: SetupRun = { provided: {}, failed: [] };
  steps.forEach((step, index) => {
    const result = results[index];
    const content = result.content.toLowerCase();
    const unnamed = step.provides.filter((name) => !content.includes(name.toLowerCase()));
    let why = '';
    if (result.outcome !== 'ok') why = `${result.outcome} ${result.code}`.trim();
    else if (unnamed.length) why = `its result does not name ${unnamed.join(', ')}`;
    if (why) {
      run.failed.push({ step: index + 1, tool: step.tool, why });
      return;
    }
    if (step.provides.length) (run.provided[entityOf(step.tool)] ??= []).push(...step.provides);
  });
  return run;
}

const CONNECTOR = '(?:de|del|la|el|los|las|para|con|en|a|al|y|un|una|como|que|por|o|QA)';
const NAME = `\\p{Lu}\\p{L}*(?:\\s(?!${CONNECTOR}\\s)\\p{L}+){0,3}\\sQA(?![-\\w])`;
const NAMES = new RegExp(`\\b[A-Z]{2,4}-\\d{8}-\\d{4}\\b|\\b\\d{8}-\\d{4}\\b|\\bQA-[A-Z0-9]+(?:-[A-Z0-9]+)*\\b|\\bproduct\\.qa\\b|${NAME}`, 'gu');

/** The records `phrase` names: names ending in «QA», QA codes, dated numbers and `product.qa`; never what is
 *  quoted («…»: a new value), and without the verb a phrase may start with. */
export function namesOf(phrase: string): string[] {
  const text = phrase.replace(/«[^»]*»/g, (quoted) => ' '.repeat(quoted.length));
  const names = [...text.matchAll(NAMES)].map((match) => {
    const words = match[0].split(' ');
    return match.index === 0 && words.length > 2 ? words.slice(1).join(' ') : match[0];
  });
  return [...new Set(names)];
}

/** Whether a corpus file only prepares the business (`owner-es-preparation-….json`): with a setup, it makes the same. */
export const isPreparation = (path: string): boolean => /(^|\/)[^/]*-preparation[^/]*\.json$/.test(path);

const made = (name: string, names: string[]): boolean => names.some((given) => given === name || given.startsWith(`${name} `));

/** Why `probe` stays out of the score after `run`: a record it names that the setup did not make, or, for a create,
 *  one the setup already made with the same kind of record (the create would be a duplicate). Empty: it is scored. */
export function missingFor(probe: Probe, run: SetupRun): string[] {
  const names = namesOf(probe.phrase);
  const entity = entityOf(probe.tool);
  if (CREATES.has(probe.tool.split('.').at(-1) ?? '')) {
    const same = run.provided[entity] ?? [];
    return names.filter((name) => made(name, same)).map((name) => `the setup already made «${name}» with ${entity}`);
  }
  const all = Object.values(run.provided).flat();
  return names.filter((name) => !made(name, all)).map((name) => `it names «${name}», which the setup does not make`);
}

/**
 * The Hub's side (`manage.py shell --hub a -c`): each step of `QA_SETUP_FILE` run as a confirmed tool call of `a`'s
 * owner, by the same runner the assistant uses (`live.assistant.run_tool`: the operation's own validation, permissions
 * and transaction). It prints one line of JSON, what each step answered.
 */
export const SETUP_PY = `
import json, os
from base.models import Membership
from base.permissions import permissions_for
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import get

scope = Scope("host", "a")
member = Membership.objects.filter(host="a", role=Membership.Role.OWNER).select_related("user").first()
if member is None:
    raise SystemExit("the setup runs as the owner of a, who has not signed in to it yet")
owner = member.user
ctx = OperationContext(scope=scope, actor=owner, permissions=permissions_for(owner, scope), language="es")
with open(os.environ["QA_SETUP_FILE"], encoding="utf-8") as handle:
    steps = json.load(handle)
results = []
for step in steps:
    outcome = shared.run_tool(ctx, get(step["tool"]), json.dumps(step["arguments"]))
    results.append({"outcome": outcome.outcome, "code": outcome.code, "content": outcome.content})
print(json.dumps(results))
`;

/** How the setup runs from the Hub's checkout, its steps (dated) in `file`. */
export function setupCommand(file: string, env: Record<string, string | undefined>): { file: string; args: string[]; env: Record<string, string> } {
  const base = Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));
  return { file: 'uv', args: ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', SETUP_PY], env: { ...base, QA_SETUP_FILE: file } };
}

/** What each step answered, from the shell's output (its last line). */
export function parseSetupRun(output: string): StepResult[] {
  return JSON.parse(output.trim().split('\n').at(-1) ?? '[]') as StepResult[];
}
