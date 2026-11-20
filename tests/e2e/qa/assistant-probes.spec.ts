// Layer 2 of the assistant's QA, with the REAL model: the PROBES of qa/probes/*.json (or `QA_PROBES`: comma-separated files or folders), one test each. A
// probe is a new natural phrase a QA agent wrote for one tool, as a person of one role types it in one language; the
// test signs in as that role (owner and employee of the SaaS's demo seed, a manager and an admin seeded here), asks it
// in a new conversation of the real chat and checks what went over the wire: the read ran, the write's card showed
// (cancelled by default: nothing changes; confirmed only when the probe says so), the role was refused what it lacks
// (checked first against the exported catalogue) or the documentation was searched and cited. Skipped unless
// QA_REAL_PROVIDER=1: it spends real tokens and never runs in CI. Needs the keys in the environment (QA_QWEN_API_KEY,
// QA_OPENAI_API_KEY; never in the repo, the report or a screenshot) and the stack's SaaS (E2E_SAAS_DIR) running with
// ASSISTANT_SERVICE_PROVIDER=openai (README «Las sondas del asistente»). A probe that does not fit the catalogue (empty
// phrase, a copy of an ask, a tool the role holds or lacks) is n.a.: no turn is asked. The QA_ANSWER_* variables
// choose the model that answers (assistant-seed.ts) and QA_PROBES_SAMPLE a sample of the files (assistant-sample.ts);
// a sampled run first makes the records its probes name (qa/setup.json, assistant-setup.ts) and leaves out of the score
// the probes whose record the setup cannot make.
// Writes `.artifacts/qa/<run>/assistant-probes.md` (the report), its JSON, `.artifacts/qa/<run>/<probe>.png` and
// `.artifacts/qa/<run>/bench.json`, the record of each turn that compares models (assistant-bench.ts).
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { observe, redact } from '../assistant-battery';
import {
  benchModel,
  type BenchMeta,
  type BenchReport,
  benchTurn,
  type Measured,
  notAsked,
  offeredCommand,
  parseOffered,
  parseUsage,
  toolKind,
  type Usage,
  USAGE_SQL,
  withTurn,
} from '../assistant-bench';
import {
  type Catalog,
  catalogKey,
  catalogsNeeded,
  exportCatalog,
  loadedProbes,
  MEMBERS,
  membersCommand,
  type Probe,
  type ProbeMeta,
  type ProbeOutcome,
  probeVerdict,
  problemsOf,
  QA_EMAILS,
  renderProbeReport,
  type Role,
} from '../assistant-probes';
import { openPanelAtHome } from '../assistant-panel';
import {
  answerOf,
  cleanUpRealProviders,
  converse,
  emptyMonth,
  noticesOf,
  run,
  SAAS_DIR,
  saasSql,
  SECRETS,
  seedRealProviders,
  TURN_MS,
} from '../assistant-real';
import { sampleChoice, sampleProbes } from '../assistant-sample';
import {
  isPreparation,
  madridToday,
  missingFor,
  parseSetup,
  parseSetupRun,
  setupCommand,
  type SetupRun,
  settled,
  withDates,
} from '../assistant-setup';
import { answerChoice } from '../assistant-seed';
import { A, api, ARTIFACTS, capture, type Credentials, EMPLOYEE, HUB_DIR, hostPage, OWNER } from '../helpers';
import { STACK } from '../stack';

const REAL = process.env.QA_REAL_PROVIDER === '1';
test.skip(!REAL, 'QA with the real model: QA_REAL_PROVIDER=1 (tests/e2e/README.md)');

/** The run the report belongs to: Playwright's, or `QA_PROBES_RUN` to ask some probes again into an earlier report. */
const RUN = (process.env.QA_PROBES_RUN || process.env.PW_RUN_ID || 'run').replace(/[^A-Za-z0-9._-]/g, '-');
const QA_DIR = join(ARTIFACTS, 'qa', RUN);
const STATE = join(QA_DIR, 'assistant-probes.json');
const REPORT = join(QA_DIR, 'assistant-probes.md');
const BENCH = join(QA_DIR, 'bench.json');
const CORPUS = join(HUB_DIR, 'tests', 'e2e', 'qa', 'probes');
const SETUP = join(HUB_DIR, 'tests', 'e2e', 'qa', 'setup.json');

/** The probe files of the run: `QA_PROBES` (files or folders, comma-separated), else every file of the corpus. */
function probeFiles(): string[] {
  const given = (process.env.QA_PROBES ?? '').split(',').map((path) => path.trim()).filter(Boolean);
  return (given.length ? given : [CORPUS]).flatMap((path) =>
    statSync(path).isDirectory()
      ? readdirSync(path)
          .filter((name) => name.endsWith('.json'))
          .sort()
          .map((name) => join(path, name))
      : [path],
  );
}

const FILES = probeFiles();
const CORPUS_PROBES: Probe[] = loadedProbes(FILES.map((path) => ({ source: relative(HUB_DIR, path), text: readFileSync(path, 'utf8') })));
const SAMPLE = sampleChoice(process.env);
const PROBES: Probe[] = SAMPLE ? sampleProbes(CORPUS_PROBES, SAMPLE) : CORPUS_PROBES;
/** The probes of the corpus's preparation files: with a setup, it makes what they made, so they are not scored. */
const PREPARATION = new Set(
  loadedProbes(FILES.filter(isPreparation).map((path) => ({ source: relative(HUB_DIR, path), text: readFileSync(path, 'utf8') }))).map((probe) => probe.id),
);

/** Who signs in for each role: the SaaS's demo accounts, and the two members the run seeds. */
const PEOPLE: Record<Role, Credentials> = { owner: OWNER, employee: EMPLOYEE, ...MEMBERS };

interface State {
  run: string;
  meta: ProbeMeta;
  prepared: boolean;
  /** What the setup of a sampled run made, once, before its first probe. */
  setup?: SetupRun;
  outcomes: Record<string, ProbeOutcome>;
}

function readState(): State | null {
  if (!existsSync(STATE)) return null;
  const state = JSON.parse(readFileSync(STATE, 'utf8')) as State;
  return state.run === RUN ? state : null;
}

function writeState(state: State): void {
  writeFileSync(STATE, redact(JSON.stringify(state, null, 2), SECRETS));
  const ordered = PROBES.map((probe) => state.outcomes[probe.id]).filter((outcome): outcome is ProbeOutcome => Boolean(outcome));
  writeFileSync(REPORT, redact(renderProbeReport(ordered, state.meta), SECRETS));
}

function save(outcome: ProbeOutcome): void {
  const kept = readState() ?? state;
  kept.outcomes[outcome.probe.id] = outcome;
  writeState(kept);
}

/**
 * On every invocation (its `afterAll` takes them out again): the real providers and the index (as the battery), and
 * the manager and the admin of `a`. The run's state and report are kept per run, so probes asked again join them.
 */
function prepare(): State {
  mkdirSync(QA_DIR, { recursive: true });
  const seeded = seedRealProviders();
  const members = membersCommand(process.env, STACK.saasDatabase);
  run(members.file, members.args, SAAS_DIR, members.env);
  const kept = readState();
  if (kept) return kept;
  const meta: ProbeMeta = {
    run: RUN,
    model: seeded.model,
    fallback: seeded.fallback,
    service: seeded.service,
    files: FILES.map((path) => relative(HUB_DIR, path)),
  };
  const state: State = { run: RUN, meta, prepared: false, outcomes: {} };
  writeState(state);
  return state;
}

/** The run's bench report as the spec starts it; a run asked again keeps the one it began with. */
const benchMeta: BenchMeta = {
  product: 'hub',
  run: RUN,
  date: new Date().toISOString(),
  model: benchModel(answerChoice(process.env)),
  files: FILES.map((path) => relative(HUB_DIR, path)),
  corpus: CORPUS_PROBES.length,
  sample: SAMPLE,
};

/** The tools a turn offers each probe's phrase, ranked by the Hub as the turn ranks them (assistant-bench.ts). */
function rankProbes(): Record<string, string[]> {
  const file = join(QA_DIR, 'offered-probes.json');
  writeFileSync(file, JSON.stringify(PROBES.map(({ id, role, language, phrase }) => ({ id, role, language, phrase }))));
  const command = offeredCommand(file, process.env);
  return parseOffered(run(command.file, command.args, HUB_DIR, command.env));
}

/** What `a` spent in the stack's SaaS since the probe emptied its month. */
const spent = (): Usage => parseUsage(saasSql(USAGE_SQL));

/** A turn that never ended is the model's failure too: its record says why, with what it streamed and spent. */
function unfinished(probe: Probe, bodies: string[], latencyMs: number, error: Error): void {
  const outcome: ProbeOutcome = { probe, answer: '', observed: observe(bodies), decided: 'none', notices: [], screenshot: '', problems: [] };
  let why = `did not finish: ${error.message.split('\n')[0]}`;
  let usage: Usage | null = null;
  try {
    usage = spent();
  } catch (unread) {
    why += `; its usage could not be read: ${(unread as Error).message.split('\n')[0]}`;
  }
  bench(outcome, { bodies, latencyMs, usage, error: why });
}

/** The setup of a sampled run (qa/setup.json), dated today, run in `a` as its owner by the Hub's tools; what it made. */
function setUp(): SetupRun {
  const steps = withDates(parseSetup(readFileSync(SETUP, 'utf8'), relative(HUB_DIR, SETUP)), madridToday(new Date()));
  const file = join(QA_DIR, 'setup-steps.json');
  writeFileSync(file, JSON.stringify(steps));
  const command = setupCommand(file, process.env);
  const made = settled(steps, parseSetupRun(run(command.file, command.args, HUB_DIR, command.env)));
  writeFileSync(join(QA_DIR, 'setup-run.json'), JSON.stringify(made, null, 2));
  return made;
}

/** Why the setup leaves `probe` out of the score (empty: it counts); nothing without a setup. */
function unscored(probe: Probe): string[] {
  if (!state.setup) return [];
  if (PREPARATION.has(probe.id)) return ['a probe of the corpus’s preparation: the setup makes what it made'];
  return missingFor(probe, state.setup);
}

/** The probe's turn into the run's bench report. */
function bench(outcome: ProbeOutcome, measured: Omit<Measured, 'kind' | 'offered'>): void {
  const kept = existsSync(BENCH) ? (JSON.parse(readFileSync(BENCH, 'utf8')) as BenchReport) : null;
  const turn = benchTurn(outcome, { ...measured, kind: toolKind(outcome.probe, catalogs), offered: offered[outcome.probe.id] ?? null });
  const setup = state.setup ? { file: relative(HUB_DIR, SETUP), failed: state.setup.failed } : null;
  const report = withTurn(kept, { ...benchMeta, setup }, turn, PROBES.map((probe) => probe.id));
  writeFileSync(BENCH, redact(JSON.stringify(report, null, 2), SECRETS));
}

/** The probe's page: signed in as its role, in its language, the assistant's panel open. A failure here is not the
 *  model's: the probe is recorded as not asked, with why, and the test fails with the error. */
async function pageFor(browser: Browser, probe: Probe): Promise<{ context: BrowserContext; page: Page }> {
  let opened: { context: BrowserContext; page: Page } | undefined;
  try {
    emptyMonth();
    opened = await hostPage(browser, A, { next: '/', credentials: PEOPLE[probe.role], viewport: { width: 1440, height: 900 } });
    await opened.context.addCookies([{ name: 'django_language', value: probe.language, domain: new URL(A).hostname, path: '/' }]);
    await openPanelAtHome(opened.page);
    return opened;
  } catch (error) {
    await opened?.context.close();
    const outcome = notAsked(probe, error as Error);
    save(outcome);
    bench(outcome, { bodies: [], latencyMs: null, usage: null, error: null });
    throw error;
  }
}

/** Every app of `a` on, as the exported catalogue assumes: turned on until none is left or none more can be. */
async function everyAppOn(context: BrowserContext): Promise<void> {
  let refused: string[] = [];
  for (let pass = 0; pass < 5; pass++) {
    const listed = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
    expect(listed.status, JSON.stringify(listed.data)).toBe(200);
    const off = listed.data.apps.filter((app) => app.state !== 'on').map((app) => app.id);
    if (!off.length) return;
    refused = [];
    for (const app of off) {
      const answer = await api(context, A, 'POST', '/apps/enable', { app });
      if (answer.status !== 200) refused.push(`${app}: ${answer.status} ${JSON.stringify(answer.data).slice(0, 200)}`);
    }
    if (refused.length === off.length) break;
  }
  expect(refused, 'apps of a that could not be turned on').toEqual([]);
}

let state: State;
const catalogs: Record<string, Catalog> = {};
let offered: Record<string, string[]> = {};

// The real keys and the QA accounts never stay in the stack's SaaS, whether the run passed or not.
test.afterAll(() => cleanUpRealProviders(QA_EMAILS));

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  state = prepare();
  for (const { role, language } of catalogsNeeded(PROBES)) catalogs[catalogKey(role, language)] = exportCatalog(role, language);
  offered = rankProbes();
  if (state.prepared) return;
  const { context } = await hostPage(browser, A, { next: '/' });
  try {
    await everyAppOn(context);
  } finally {
    await context.close();
  }
  if (SAMPLE) state.setup = setUp();
  state.prepared = true;
  writeState(state);
});

for (const probe of PROBES) {
  test(`${probe.id} — ${probe.expect} ${probe.tool} as ${probe.role} (${probe.language}) — ${probe.phrase}`, async ({ browser }) => {
    test.setTimeout(TURN_MS + 180_000);
    const screenshot = join(QA_DIR, `${probe.id}.png`);
    const problems = [...problemsOf(probe, catalogs), ...unscored(probe)];
    if (problems.length) {
      const outcome: ProbeOutcome = { probe, answer: '', observed: observe([]), decided: 'none', notices: [], screenshot: '', problems };
      save(outcome);
      bench(outcome, { bodies: [], latencyMs: null, usage: null, error: null });
      test.skip(true, `the probe does not fit the catalogue: ${problems.join('; ')}`);
      return;
    }
    const { context, page } = await pageFor(browser, probe);
    try {
      const bodies: string[] = [];
      const started = Date.now();
      let said: Awaited<ReturnType<typeof converse>>;
      try {
        said = await converse(page, probe.phrase, probe.decide ?? 'cancel', probe.id, bodies);
      } catch (error) {
        unfinished(probe, bodies, Date.now() - started, error as Error);
        throw error;
      }
      const { decided } = said;
      const outcome: ProbeOutcome = {
        probe,
        answer: await answerOf(page),
        observed: observe(bodies),
        decided,
        notices: await noticesOf(page),
        screenshot,
        problems: [],
      };
      try {
        await capture(page, `qa/${RUN}/${probe.id}`);
      } catch (error) {
        outcome.screenshot = `(not captured: ${(error as Error).message.slice(0, 200)})`;
      }
      save(outcome);
      bench(outcome, { bodies, latencyMs: said.endedAt - started, usage: spent(), error: null });
      const verdict = probeVerdict(outcome);
      expect(verdict.verdict, `${probe.id}: ${verdict.reasons.join('; ')} (chosen: ${verdict.chosen})`).toBe('PASS');
    } finally {
      await context.close();
    }
  });
}
