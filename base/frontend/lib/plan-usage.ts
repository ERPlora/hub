// What System › «Usage and plan» says from the figures (BASE-F40): the line at the top, which tells whoever runs the
// business whether to upgrade, and the rows of what the plan includes, the fullest first. The same reading paints both,
// so a bar's colour never says something the line does not.
//
// - Red, «You have to upgrade»: files full, the assistant's or an app's messages spent this month, or a capacity that fell
//   short in 7 days when a bigger plan would give more. Amber, «You should upgrade»: files or those messages from 80 %.
// - People, devices and apps at their limit say «Full» on their row and never change the colour: a Free business with its
//   one device in use is fine, and that alarm would never go away.
// - Capacity never goes by its percentage, only by the times it fell short: with a limit of 1 the first operation is its
//   100 %. And on a plan with all the service gives there is nothing to upgrade to.
// - What the plan does not include, could not be read or was not measured yet is no motive.
//
// The bell's row tells the same from the server, without what waits on erplora.com (`base.queries._plan_motives`).
import type { AssistantUsage, PlanMeter, PlanUsage } from '../operations';

/** From here on what a plan includes is close to its limit: the server's `base.queries.NEAR_PERCENT`. */
export const NEAR_PERCENT = 80;

/** The assistant's messages, which the screen asks apart because they wait on erplora.com: null until they answer. */
export type AssistantRead = AssistantUsage | null | 'failed';

export type VerdictTone = 'danger' | 'warning' | 'success';
type MotiveTone = Exclude<VerdictTone, 'success'>;

export interface Motive {
  /** `files`, `assistant`, `capacity` or the app of a meter. */
  key: string;
  kind: 'files' | 'assistant' | 'capacity' | 'meter';
  /** What a meter is called. */
  label: string | null;
  tone: MotiveTone;
  /** How full, to tell apart motives of the same gravity. */
  fullness: number;
}

export type FullThing = 'people' | 'devices' | 'apps';

export interface UsageVerdict {
  tone: VerdictTone;
  /** The most serious reason to upgrade and, among equals, the fullest. */
  motive: Motive | null;
  /** What is at its limit and never changes the colour. */
  full: FullThing[];
}

export type RowState = 'measured' | 'noLimit' | 'notIncluded' | 'notMeasured' | 'unavailable' | 'loading' | 'plain';

export interface UsageRow {
  id: string;
  kind: 'files' | 'apps' | 'people' | 'devices' | 'assistant' | 'meter' | 'capacity';
  /** What a meter is called. */
  label: string | null;
  used: number | null;
  limit: number | null;
  /** How full; null: no bar. */
  percent: number | null;
  tone: VerdictTone;
  pill: 'near' | 'full' | null;
  state: RowState;
}

/** How a monthly allowance stands; null: nothing to say of it. */
function messagesTone(used: number | null, limit: number | null): MotiveTone | 'success' | null {
  if (used === null || !limit) return null;
  const percent = (used / limit) * 100;
  if (percent >= 100) return 'danger';
  return percent >= NEAR_PERCENT ? 'warning' : 'success';
}

const fellShort = (usage: PlanUsage): boolean =>
  usage.connections.bigger_plan_gives_more && (usage.connections.busy_last_7_days ?? 0) > 0;

const GRAVITY: Record<MotiveTone, number> = { danger: 1, warning: 0 };

export function verdictOf(usage: PlanUsage, assistant: AssistantRead): UsageVerdict {
  const motives: Motive[] = [];
  const { status, percent } = usage.files;
  if (status === 'full' || status === 'near') {
    motives.push({
      key: 'files',
      kind: 'files',
      label: null,
      tone: status === 'full' ? 'danger' : 'warning',
      fullness: percent ?? 0,
    });
  }
  const allowance = (kind: Motive['kind'], key: string, label: string | null, used: number | null, limit: number | null) => {
    const tone = messagesTone(used, limit);
    if (tone === 'danger' || tone === 'warning') {
      motives.push({ key, kind, label, tone, fullness: ((used ?? 0) / (limit ?? 1)) * 100 });
    }
  };
  if (assistant && assistant !== 'failed') allowance('assistant', 'assistant', null, assistant.used, assistant.limit);
  for (const meter of usage.meters) allowance('meter', meter.key, meter.label, meter.used, meter.limit);
  if (fellShort(usage)) motives.push({ key: 'capacity', kind: 'capacity', label: null, tone: 'danger', fullness: 100 });

  const [motive] = [...motives].sort((a, b) => GRAVITY[b.tone] - GRAVITY[a.tone] || b.fullness - a.fullness);
  const full = (['people', 'devices', 'apps'] as const).filter((thing) => {
    const { used, limit } = usage[thing];
    return limit !== null && used !== null && used >= limit;
  });
  return { tone: motive?.tone ?? 'success', motive: motive ?? null, full };
}

function row(id: string, kind: UsageRow['kind'], fields: Partial<UsageRow>): UsageRow {
  return { id, kind, label: null, used: null, limit: null, percent: null, tone: 'success', pill: null, state: 'measured', ...fields };
}

function seats(kind: FullThing, usage: PlanUsage): UsageRow {
  const { used, limit } = usage[kind];
  if (limit === null) return row(kind, kind, { used, state: 'noLimit' });
  const percent = ((used ?? 0) / limit) * 100;
  return row(kind, kind, { used, limit, percent, pill: percent >= 100 ? 'full' : null });
}

function files(usage: PlanUsage): UsageRow {
  const { bytes, limit, percent, status } = usage.files;
  if (bytes === null) return row('files', 'files', { limit, state: 'notMeasured' });
  if (limit === null || status === null) return row('files', 'files', { used: bytes, state: 'noLimit' });
  const tone = status === 'full' ? 'danger' : status === 'near' ? 'warning' : 'success';
  return row('files', 'files', { used: bytes, limit, percent, tone, pill: status === 'within' ? null : status });
}

function messages(id: string, kind: UsageRow['kind'], label: string | null, used: number, limit: number): UsageRow {
  if (limit === 0) return row(id, kind, { label, used, limit, state: 'notIncluded' });
  const tone = messagesTone(used, limit) ?? 'success';
  const pill = tone === 'danger' ? 'full' : tone === 'warning' ? 'near' : null;
  return row(id, kind, { label, used, limit, percent: (used / limit) * 100, tone, pill });
}

function assistantRow(read: AssistantRead): UsageRow {
  if (read === null) return row('assistant', 'assistant', { state: 'loading' });
  if (read === 'failed') return row('assistant', 'assistant', { state: 'unavailable' });
  return messages('assistant', 'assistant', null, read.used, read.limit);
}

function meterRow({ key, label, used, limit, available }: PlanMeter): UsageRow {
  if (!available) return row(key, 'meter', { label, state: 'unavailable' });
  if (used === null || limit === null) return row(key, 'meter', { label, state: 'notMeasured' });
  return messages(key, 'meter', label, used, limit);
}

function capacity(usage: PlanUsage): UsageRow {
  const { peak_today: peak, limit } = usage.connections;
  if (peak === null) return row('capacity', 'capacity', { limit, state: 'notMeasured' });
  if (limit === null) return row('capacity', 'capacity', { used: peak, state: 'noLimit' });
  return row('capacity', 'capacity', {
    used: peak,
    limit,
    percent: (peak / limit) * 100,
    tone: fellShort(usage) ? 'danger' : 'success',
  });
}

/** Where a row goes: the fullest first, then what has no bar; capacity goes by the times it fell short, never by how full. */
function fullness(item: UsageRow, usage: PlanUsage): number {
  if (item.kind === 'capacity') return fellShort(usage) ? 100 : -2;
  return item.percent ?? -1;
}

/** What is in use, with no limit, bar or pill, while the Hub does not know the plan. */
function withoutThePlan(usage: PlanUsage): UsageRow[] {
  const plain = (item: UsageRow): UsageRow => (item.used === null ? item : { ...item, limit: null, percent: null, pill: null, tone: 'success', state: 'plain' });
  return [files(usage), seats('apps', usage), seats('people', usage), seats('devices', usage), capacity(usage)].map(plain);
}

export function usageRows(usage: PlanUsage, assistant: AssistantRead): UsageRow[] {
  if (!usage.known) return withoutThePlan(usage);
  const rows = [
    files(usage),
    seats('apps', usage),
    seats('people', usage),
    assistantRow(assistant),
    ...usage.meters.map(meterRow),
    seats('devices', usage),
    capacity(usage),
  ];
  return rows
    .map((item, index) => ({ item, index, score: fullness(item, usage) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(({ item }) => item);
}
