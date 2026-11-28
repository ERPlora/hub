// One line per step of a run's History (WORKBOOK FLOW-F16), in words: each step by what it does, never by the id it
// has inside the automation. A call to another system or a request to the assistant has its line while it goes on
// («Calling api.example.com…»); once that step says how it went, only that is said.
import type { CatalogOut, LogEntry, Step } from '../operations';
import { actionLabel, describeClause, describeDuration, describeStep, fieldLabel, formatDate, type Phrasing, quoted } from './phrasing';

/** What a line is said with: the automation's steps, the catalog and the words of the screen. */
export interface LogWords {
  steps: readonly Step[];
  catalog: CatalogOut | null | undefined;
  p: Phrasing;
}

type Line = (entry: LogEntry, w: LogWords) => string;

const action = (entry: LogEntry, w: LogWords): string => (entry.operation ? actionLabel(entry.operation, w.catalog, w.p) : '');
const until = (entry: LogEntry, w: LogWords): string => formatDate(entry.until ?? entry.at, w.p.locale, w.p.timeZone);
const clauses = (entry: LogEntry, w: LogWords): string => (entry.failed ?? []).map((clause) => describeClause(clause, w.steps, w.catalog, w.p)).join('; ');

function answered(entry: LogEntry, w: LogWords): string {
  const said = w.p.t(entry.approved ? 'flow.history.log.answeredYes' : 'flow.history.log.answeredNo', { who: entry.by ?? '' });
  return entry.note ? `${said}: ${quoted(entry.note, w.p)}` : said;
}

/** The lines said only while their step goes on. */
const GOING_ON: ReadonlySet<LogEntry['outcome']> = new Set(['calling', 'thinking']);

/** The step a line speaks of: its action, or what it does («Call api.example.com»); by its kind if it is gone. */
function stepName(entry: LogEntry, w: LogWords): string {
  const named = action(entry, w);
  if (named) return named;
  const step = w.steps.find((candidate) => candidate.id === entry.step);
  if (step) return describeStep(step, w.steps, w.catalog, w.p);
  return entry.kind === 'http' && entry.host ? w.p.t('flow.steps.describe.http', { host: entry.host }) : w.p.t(`flow.steps.add.${entry.kind}`);
}

function failed(entry: LogEntry, w: LogWords): string {
  const said = w.p.t('flow.history.log.failed', { action: stepName(entry, w), message: entry.error?.message ?? '' });
  return entry.continued ? `${said} ${w.p.t('flow.history.log.continued')}` : said;
}

const LINES: Partial<Record<LogEntry['outcome'], Line>> = {
  done: (entry, w) => w.p.t('flow.history.log.done', { action: action(entry, w) }),
  found: (entry, w) => w.p.t('flow.history.log.found', { n: entry.count ?? 1 }),
  not_found: (_, w) => w.p.t('flow.history.log.not_found'),
  passed: (_, w) => w.p.t('flow.history.log.passed'),
  stopped: (entry, w) => w.p.t('flow.history.log.stopped', { clauses: clauses(entry, w) }),
  waiting: (entry, w) => w.p.t('flow.history.log.waiting', { date: until(entry, w) }),
  waited: (entry, w) => w.p.t('flow.history.log.waited', { duration: describeDuration(entry.seconds ?? 0, w.p) }),
  resumed: (_, w) => w.p.t('flow.history.log.resumed'),
  calling: (entry, w) => w.p.t('flow.history.log.calling', { host: entry.host ?? '' }),
  called: (entry, w) => w.p.t('flow.history.log.called', { host: entry.host ?? '', status: entry.status ?? '' }),
  asking: (entry, w) => w.p.t('flow.history.log.asking', { who: w.p.t(`flow.ask.roles.${entry.role || 'admin'}`), date: until(entry, w) }),
  answered,
  expired: (_, w) => w.p.t('flow.history.log.expired'),
  thinking: (_, w) => w.p.t('flow.history.log.thinking'),
  assistant_used: (entry, w) => w.p.t(entry.ok ? 'flow.history.log.assistantUsed' : 'flow.history.log.assistantRefused', { action: action(entry, w) }),
  assistant_answered: (entry, w) => w.p.t('flow.history.log.assistantAnswered', { text: entry.text ?? '' }),
  assistant_proposed: (entry, w) => w.p.t('flow.history.log.assistantProposed', { action: action(entry, w), date: until(entry, w) }),
  assistant_pinned_empty: (entry, w) =>
    w.p.t('flow.history.log.assistantPinnedEmpty', { action: action(entry, w), fields: (entry.fields ?? []).map((name) => quoted(fieldLabel(name, w.p), w.p)).join(', ') }),
  skipped: (entry, w) => w.p.t('flow.history.log.skipped', { clauses: clauses(entry, w) }),
};

/** One line of a run's history, in words. */
export function describeLog(entry: LogEntry, w: LogWords): string {
  return (LINES[entry.outcome] ?? failed)(entry, w);
}

/** The run's lines, without the one of a step still going on once that step has said how it went. */
export function historyLines(log: readonly LogEntry[], w: LogWords): string[] {
  const over = (entry: LogEntry, index: number): boolean => GOING_ON.has(entry.outcome) && log.slice(index + 1).some((later) => later.step === entry.step);
  return log.filter((entry, index) => !over(entry, index)).map((entry) => describeLog(entry, w));
}
