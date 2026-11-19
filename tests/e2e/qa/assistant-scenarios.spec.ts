// The assistant's QA as real use: each SCENARIO of qa/scenarios/*.json (or `QA_SCENARIOS`: comma-separated files) is a
// whole job a business owner asks for in plain words, in one conversation of the real chat, sometimes with a file
// attached through the real composer. A simulated owner (assistant-owner.ts) answers the assistant from its facts only;
// it always confirms the cards, typing the word on a high-risk one. The job is scored from the business's database at
// the end and from what went over the wire (assistant-scenario-score.ts).
// Every scenario starts from the same business: a copy of `a`'s database taken in `beforeAll` and put back before each
// scenario (assistant-snapshot.ts), then its seed and setup made by the Hub's tools with no model. First its golden path
// runs there (the calls a perfect assistant would make, through the assistant's own turn) and its checks must hold: if
// not, the scenario is excluded, the same for every model. Then the business is put back and the model is asked, unless
// a precheck says it cannot be (assistant-precheck.ts). Nothing ever reaches the tax agency: the run refuses a Hub with
// a VeriFactu gateway, and every scenario ends checking that no fiscal record left the business.
// `QA_SCENARIOS_GOLDEN=1` runs only the golden paths (no model, no keys). With the model, QA_REAL_PROVIDER=1, the keys
// and the stack's SaaS, as the probes (README «Los escenarios del asistente»). Writes `.artifacts/qa/<run>/bench.json`.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { type Browser, expect, type Page, test } from '@playwright/test';

import { QA_STAFF_EMAIL, redact } from '../assistant-battery';
import { benchModel, type BenchMeta, type BenchReport, parseUsage, USAGE_SQL } from '../assistant-bench';
import { type AttachedFile, attachmentFile, renderWith } from '../assistant-fixtures';
import { goldenCommand, parseStepResults, runSteps, type StepsRun } from '../assistant-golden';
import { askOwner, type Exchange, ownerChoice, type OwnerDeps } from '../assistant-owner';
import { notRunnable, offeredTurnCommand, openingContent, parseOfferedTurn, SENT_SQL } from '../assistant-precheck';
import { cleanUpRealProviders, converse, emptyMonth, openPanel, run, saasSql, SECRETS, seedRealProviders, TURN_MS } from '../assistant-real';
import { type Check, loadedScenarios, type Scenario, type ToolStep } from '../assistant-scenario';
import { datedScenario } from '../assistant-scenario-dates';
import { type EndedBy, type ScenarioMeasured, scenarioRow, withScenario } from '../assistant-scenario-bench';
import { checked, type CheckResult, scoreScenario, type ScenarioTurn } from '../assistant-scenario-score';
import { cardLine, scenarioTurn } from '../assistant-scenario-turn';
import { answerChoice } from '../assistant-seed';
import { madridToday } from '../assistant-setup';
import { copyCountStatement, dropCopyStatements, onServer, restoreStatements, snapshotStatements } from '../assistant-snapshot';
import { A, ARTIFACTS, capture, HUB_DIR, hostPage, psql, REPO_DIR } from '../helpers';

const REAL = process.env.QA_REAL_PROVIDER === '1';
const GOLDEN = process.env.QA_SCENARIOS_GOLDEN === '1';
test.skip(!REAL && !GOLDEN, 'scenarios: QA_REAL_PROVIDER=1 with the model, or QA_SCENARIOS_GOLDEN=1 for their golden paths (tests/e2e/README.md)');
// A card whose button never becomes usable ends the conversation with why, instead of holding the test to its timeout.
test.use({ actionTimeout: 60_000 });

const RUN = (process.env.QA_SCENARIOS_RUN || process.env.PW_RUN_ID || 'run').replace(/[^A-Za-z0-9._-]/g, '-');
const QA_DIR = join(ARTIFACTS, 'qa', RUN);
const BENCH = join(QA_DIR, 'bench.json');
const CORPUS = join(HUB_DIR, 'tests', 'e2e', 'qa', 'scenarios');
const GIVEN = (process.env.QA_SCENARIOS ?? '').split(',').map((path) => path.trim()).filter(Boolean);
const FILES = GIVEN.length ? GIVEN : readdirSync(CORPUS).filter((name) => name.endsWith('.json')).sort().map((name) => join(CORPUS, name));
const SCENARIOS = loadedScenarios(FILES.map((path) => ({ source: relative(HUB_DIR, path), text: readFileSync(path, 'utf8') })));
const ORDER = SCENARIOS.map((scenario) => scenario.id);
let business = '';
/** `a`'s own database, the one every scenario starts from a copy of. */
const businessDb = (): string => (business ||= psql("select db_name from base_hub where slug = 'a'"));

type Checks = { expect: CheckResult[]; forbidden: CheckResult[] };

/** A batch of steps run in `a` as its owner (assistant-golden.ts), its file kept in the run's folder. */
function executor(mode: 'setup' | 'golden', language: string) {
  return (batch: ToolStep[]) => {
    const file = join(QA_DIR, `steps-${mode}.json`);
    writeFileSync(file, JSON.stringify(batch));
    const command = goldenCommand({ file, mode, language }, process.env);
    return parseStepResults(run(command.file, command.args, HUB_DIR, command.env));
  };
}

const hasCopy = (): boolean => onServer([copyCountStatement(businessDb())], REPO_DIR) === '1';

/** `a` put back from the run's copy; without the copy nothing is dropped. */
function putBack(): void {
  if (!hasCopy()) throw new Error(`there is no copy of ${businessDb()} to put back: the run's beforeAll did not make it`);
  onServer(restoreStatements(businessDb()), REPO_DIR);
}

const read = (sql: string): string | Error => {
  try {
    return psql(sql);
  } catch (error) {
    return error as Error;
  }
};

/** `a` put back as the run found it, then the scenario's seed and setup; the values its `unchanged` checks start from. */
function prepared(scenario: Scenario): { setup: StepsRun; before: Map<string, string> } {
  putBack();
  const steps = [{ tool: 'base.blueprint.import', arguments: { template: scenario.seed } }, ...scenario.setup];
  const setup = runSteps(steps, executor('setup', scenario.language));
  const before = new Map<string, string>();
  for (const check of [...scenario.expect, ...scenario.forbidden].filter((one) => one.unchanged)) {
    const value = read(check.sql);
    if (typeof value === 'string') before.set(check.sql, value);
  }
  return { setup, before };
}

const checksOf = (scenario: Scenario, before: Map<string, string>): Checks => {
  const result = (check: Check) => checked(check, read(check.sql), before.get(check.sql) ?? null);
  return { expect: scenario.expect.map(result), forbidden: scenario.forbidden.map(result) };
};

const failedOf = (checks: Checks): string[] => [...checks.expect, ...checks.forbidden].filter((one) => !one.ok).map((one) => `${one.says} (got ${one.got}, want ${one.want})`);

/** Why the scenario cannot be passed on this stack by any model (its setup or golden path failed), or null. */
function goldenProblem(scenario: Scenario): string | null {
  const { setup, before } = prepared(scenario);
  if (setup.failed) return `setup step ${setup.failed.step - 1} (${setup.failed.tool}) failed: ${setup.failed.why}`;
  const golden = runSteps(scenario.golden, executor('golden', scenario.language));
  if (golden.failed) return `golden path step ${golden.failed.step} (${golden.failed.tool}) failed: ${golden.failed.why}`;
  const failed = failedOf(checksOf(scenario, before));
  return failed.length ? `golden path ends with checks failing: ${failed.join('; ')}` : null;
}

function bench(scenario: Scenario, measured: ScenarioMeasured): void {
  const meta: BenchMeta = {
    product: 'hub',
    run: RUN,
    date: new Date().toISOString(),
    model: benchModel(answerChoice(process.env)),
    files: FILES.map((path) => relative(HUB_DIR, path)),
    corpus: SCENARIOS.length,
    sample: null,
    owner: { model: ownerChoice(process.env).model },
  };
  const kept = existsSync(BENCH) ? (JSON.parse(readFileSync(BENCH, 'utf8')) as BenchReport) : null;
  const report = withScenario(kept, meta, scenarioRow(scenario, measured), ORDER);
  writeFileSync(BENCH, redact(JSON.stringify(report, null, 2), SECRETS));
}

/** The scenario's files, made by its fixtures; a delivery note printed on a page of its own. */
async function filesOf(browser: Browser, scenario: Scenario): Promise<AttachedFile[]> {
  if (!scenario.attachments.length) return [];
  const printer = await browser.newPage();
  try {
    const render = renderWith(printer, (options) => capture(printer, `qa/${RUN}/${scenario.id}-photo`, options));
    return await Promise.all(scenario.attachments.map((attachment) => attachmentFile(attachment, render)));
  } finally {
    await printer.close();
  }
}

/** The tools the assistant's turn offers the opening message with its files, as the owner of `a`; null when the
 *  scenario names none its opening needs. */
function offeredFor(scenario: Scenario, files: AttachedFile[]): string[] | null {
  if (!scenario.offered.length) return null;
  const file = join(QA_DIR, `opening-${scenario.id}.json`);
  writeFileSync(file, JSON.stringify(openingContent(scenario.opening, files)));
  const command = offeredTurnCommand({ file, language: scenario.language }, process.env);
  return parseOfferedTurn(run(command.file, command.args, HUB_DIR, command.env));
}

/** The month's messages of `a` back to none, its tokens and cost kept: a long conversation never runs out of them. */
const enoughMessages = (): string => saasSql("update assistant_assistantusage set messages = 0 where hub_id = (select id from hubs_hub where slug = 'a')");

async function attach(page: Page, files: AttachedFile[]): Promise<void> {
  if (!files.length) return;
  await page.locator('[data-testid="assistant-attach-input"]').setInputFiles(files);
  await expect(page.locator('[data-testid="assistant-file"]')).toHaveCount(files.length);
}

interface Talked {
  turns: ScenarioTurn[];
  endedBy: EndedBy;
  owner: { tokensIn: number; tokensOut: number; costUsd: number | null };
  error: string | null;
}

/** The whole conversation: the opening with its files, then the owner's answers, until it ends or the turns run out. */
async function conversation(page: Page, scenario: Scenario, files: AttachedFile[], deps: OwnerDeps): Promise<Talked> {
  const talked: Talked = { turns: [], endedBy: 'turn_limit', owner: { tokensIn: 0, tokensOut: 0, costUsd: 0 }, error: null };
  const seen: Exchange[] = [];
  let message = scenario.opening;
  for (let index = 0; index < scenario.maxTurns; index++) {
    enoughMessages();
    await attach(page, index ? [] : files);
    const bodies: string[] = [];
    try {
      await converse(page, message, 'confirm', `${scenario.id} turn ${index + 1}`, bodies);
    } catch (error) {
      talked.turns.push(scenarioTurn(message, bodies));
      return { ...talked, endedBy: 'error', error: (error as Error).message.split('\n')[0] };
    }
    const turn = scenarioTurn(message, bodies);
    talked.turns.push(turn);
    seen.push({ who: 'owner', text: message }, { who: 'assistant', text: turn.assistant, cards: turn.cards.map((card) => cardLine(card, scenario.language)) });
    if (index + 1 === scenario.maxTurns) break;
    let reply: Awaited<ReturnType<typeof askOwner>>;
    try {
      reply = await askOwner(deps, scenario, seen);
    } catch (error) {
      return { ...talked, endedBy: 'error', error: redact((error as Error).message, SECRETS) };
    }
    talked.owner.tokensIn += reply.tokensIn;
    talked.owner.tokensOut += reply.tokensOut;
    talked.owner.costUsd = talked.owner.costUsd === null || reply.costUsd === null ? null : talked.owner.costUsd + reply.costUsd;
    if (reply.end) return { ...talked, endedBy: reply.end };
    message = reply.say ?? '';
  }
  return talked;
}

async function asked(browser: Browser, scenario: Scenario, files: AttachedFile[]): Promise<ScenarioMeasured> {
  const { setup, before } = prepared(scenario);
  expect(setup.failed, 'the setup ran in the golden check, so it runs now').toBeNull();
  emptyMonth();
  const choice = ownerChoice(process.env);
  const deps: OwnerDeps = { fetcher: fetch, choice, key: process.env[choice.keyEnv] ?? '' };
  const started = Date.now();
  const { context, page } = await hostPage(browser, A, { next: '/', viewport: { width: 1440, height: 900 } });
  try {
    await context.addCookies([{ name: 'django_language', value: scenario.language, domain: new URL(A).hostname, path: '/' }]);
    await openPanel(page);
    const talked = await conversation(page, scenario, files, deps);
    const wallMs = Date.now() - started;
    await capture(page, `qa/${RUN}/${scenario.id}`).catch(() => undefined);
    const checks = checksOf(scenario, before);
    const turns = talked.turns.map((turn, index) => (index === talked.turns.length - 1 && talked.error ? { ...turn, errors: [...turn.errors, talked.error] } : turn));
    const score = scoreScenario(scenario, checks, turns);
    return { status: 'scored', why: null, score, checks, turns, endedBy: talked.endedBy, wallMs, usage: parseUsage(saasSql(USAGE_SQL)), owner: talked.owner };
  } finally {
    // The scenario is measured by now: a context that cannot save its trace says so and loses nothing.
    await context.close().catch((error: Error) => console.warn(`${scenario.id}: the browser context did not close: ${error.message}`));
  }
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  mkdirSync(QA_DIR, { recursive: true });
  expect(process.env.VERIFACTU_GATEWAY_URL ?? '', 'a scenario run never has a VeriFactu gateway').toBe('');
  const configured = run('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', 'from apps.verifactu import gateway; print(gateway.configured())'], HUB_DIR, process.env);
  expect(configured.trim().split('\n').at(-1), 'the Hub of the stack has a VeriFactu gateway: unset VERIFACTU_GATEWAY_URL').toBe('False');
  if (REAL) seedRealProviders();
  // The owner signs in once, so its membership exists before the copy every scenario starts from.
  const { context } = await hostPage(browser, A, { next: '/' });
  await context.close();
  // A copy left by a run that never reached its afterAll is the clean business: `a` goes back to it, not the reverse.
  if (hasCopy()) putBack();
  else onServer(snapshotStatements(businessDb()), REPO_DIR);
});

test.afterAll(() => {
  if (hasCopy()) onServer([...restoreStatements(businessDb()), ...dropCopyStatements(businessDb())], REPO_DIR);
  if (REAL) cleanUpRealProviders([QA_STAFF_EMAIL]);
});

for (const scenario of SCENARIOS) {
  test(`${scenario.id} — ${scenario.title}`, async ({ browser }) => {
    test.setTimeout(scenario.maxTurns * (TURN_MS + 60_000) + 600_000);
    const dated = datedScenario(scenario, madridToday(new Date()));
    const problem = goldenProblem(dated);
    writeFileSync(join(QA_DIR, `golden-${scenario.id}.json`), JSON.stringify({ scenario: scenario.id, ok: !problem, why: problem }, null, 2));
    expect(psql(SENT_SQL), 'no fiscal record ever leaves the business').toBe('0');
    if (GOLDEN) {
      expect(problem, `${scenario.id}: its golden path must pass`).toBeNull();
      return;
    }
    if (problem) {
      bench(dated, { status: 'excluded', why: problem });
      test.skip(true, `excluded: ${problem}`);
    }
    const files = await filesOf(browser, dated);
    const why = notRunnable(dated, offeredFor(dated, files), answerChoice(process.env).vision);
    if (why) {
      bench(dated, { status: 'not_runnable', why });
      test.skip(true, why);
    }
    const measured = await asked(browser, dated, files);
    bench(dated, measured);
    expect(psql(SENT_SQL), 'no fiscal record ever leaves the business').toBe('0');
    const { score } = measured;
    expect(score?.done, `${scenario.id}: ${failedOf(measured.checks ?? { expect: [], forbidden: [] }).join('; ')}`).toBe(true);
  });
}
