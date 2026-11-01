// Layer 2 of the assistant's QA with the REAL model (docs plan 2026-10-31 of erplora-next, the assistant's knowledge
// and QA, §1.5): the PROBES of qa/probes/*.json (or `QA_PROBES`: comma-separated files or folders), one test each. A
// probe is a new natural phrase a QA agent wrote for one tool, as a person of one role types it in one language; the
// test signs in as that role (owner and employee of the SaaS's demo seed, a manager and an admin seeded here), asks it
// in a new conversation of the real chat and checks what went over the wire: the read ran, the write's card showed
// (cancelled by default: nothing changes; confirmed only when the probe says so), the role was refused what it lacks
// (checked first against the exported catalogue) or the documentation was searched and cited. Skipped unless
// QA_REAL_PROVIDER=1: it spends real tokens and never runs in CI. Needs the keys in the environment (QA_QWEN_API_KEY,
// QA_OPENAI_API_KEY; never in the repo, the report or a screenshot) and the stack's SaaS (E2E_SAAS_DIR) running with
// ASSISTANT_SERVICE_PROVIDER=openai (README «Las sondas del asistente»). A probe that does not fit the catalogue (empty
// phrase, a copy of an ask, a tool the role holds or lacks) is n.a.: no turn is asked. Writes
// `.artifacts/qa/<run>/assistant-probes.md` (the report), its JSON and `.artifacts/qa/<run>/<probe>.png`.
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { type BrowserContext, expect, test } from '@playwright/test';

import { observe, redact } from '../assistant-battery';
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
import {
  answerOf,
  cleanUpRealProviders,
  converse,
  emptyMonth,
  noticesOf,
  openPanel,
  run,
  SAAS_DIR,
  SECRETS,
  seedRealProviders,
  TURN_MS,
} from '../assistant-real';
import { A, api, ARTIFACTS, capture, type Credentials, EMPLOYEE, HUB_DIR, hostPage, OWNER } from '../helpers';
import { STACK } from '../stack';

const REAL = process.env.QA_REAL_PROVIDER === '1';
test.skip(!REAL, 'QA with the real model: QA_REAL_PROVIDER=1 (tests/e2e/README.md)');

/** The run the report belongs to: Playwright's, or `QA_PROBES_RUN` to ask some probes again into an earlier report. */
const RUN = (process.env.QA_PROBES_RUN || process.env.PW_RUN_ID || 'run').replace(/[^A-Za-z0-9._-]/g, '-');
const QA_DIR = join(ARTIFACTS, 'qa', RUN);
const STATE = join(QA_DIR, 'assistant-probes.json');
const REPORT = join(QA_DIR, 'assistant-probes.md');
const CORPUS = join(HUB_DIR, 'tests', 'e2e', 'qa', 'probes');

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
const PROBES: Probe[] = loadedProbes(FILES.map((path) => ({ source: relative(HUB_DIR, path), text: readFileSync(path, 'utf8') })));

/** Who signs in for each role: the SaaS's demo accounts, and the two members the run seeds. */
const PEOPLE: Record<Role, Credentials> = { owner: OWNER, employee: EMPLOYEE, ...MEMBERS };

interface State {
  run: string;
  meta: ProbeMeta;
  prepared: boolean;
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

// The real keys and the QA accounts never stay in the stack's SaaS, whether the run passed or not.
test.afterAll(() => cleanUpRealProviders(QA_EMAILS));

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  state = prepare();
  for (const { role, language } of catalogsNeeded(PROBES)) catalogs[catalogKey(role, language)] = exportCatalog(role, language);
  if (state.prepared) return;
  const { context } = await hostPage(browser, A, { next: '/' });
  try {
    await everyAppOn(context);
  } finally {
    await context.close();
  }
  state.prepared = true;
  writeState(state);
});

for (const probe of PROBES) {
  test(`${probe.id} — ${probe.expect} ${probe.tool} as ${probe.role} (${probe.language}) — ${probe.phrase}`, async ({ browser }) => {
    test.setTimeout(TURN_MS + 180_000);
    const screenshot = join(QA_DIR, `${probe.id}.png`);
    const problems = problemsOf(probe, catalogs);
    if (problems.length) {
      save({ probe, answer: '', observed: observe([]), decided: 'none', notices: [], screenshot: '', problems });
      test.skip(true, `the probe does not fit the catalogue: ${problems.join('; ')}`);
      return;
    }
    emptyMonth();
    const { context, page } = await hostPage(browser, A, {
      next: '/',
      credentials: PEOPLE[probe.role],
      viewport: { width: 1440, height: 900 },
    });
    try {
      await context.addCookies([{ name: 'django_language', value: probe.language, domain: new URL(A).hostname, path: '/' }]);
      await openPanel(page);
      const { bodies, decided } = await converse(page, probe.phrase, probe.decide ?? 'cancel', probe.id);
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
      const verdict = probeVerdict(outcome);
      expect(verdict.verdict, `${probe.id}: ${verdict.reasons.join('; ')} (chosen: ${verdict.chosen})`).toBe('PASS');
    } finally {
      await context.close();
    }
  });
}
