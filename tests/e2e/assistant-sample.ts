// The sample of the probe corpus a run asks, so several models answer exactly the same phrases: `QA_PROBES_SAMPLE`
// probes drawn with `QA_PROBES_SEED` (1 by default). It reaches every app, role, language and expectation first, then
// keeps each near its share of the corpus. The same corpus and seed always draw the same probes. Pure, so Vitest
// proves it (assistant-sample.test.ts).
import { type Probe, random, shuffled } from './assistant-probes.ts';

export interface SampleChoice {
  size: number;
  seed: number;
}

const DIMENSIONS = ['app', 'role', 'language', 'expect'] as const;
const WHOLE = /^\d+$/;

/** The sample asked by the environment, or null to ask every probe of the files. */
export function sampleChoice(env: Record<string, string | undefined>): SampleChoice | null {
  const size = env.QA_PROBES_SAMPLE?.trim() ?? '';
  const seed = env.QA_PROBES_SEED?.trim() ?? '';
  if (!size) {
    if (seed) throw new Error('QA_PROBES_SEED without QA_PROBES_SAMPLE: say how many probes to draw.');
    return null;
  }
  if (!WHOLE.test(size) || Number(size) < 1) throw new Error(`QA_PROBES_SAMPLE «${size}» is not a number of probes.`);
  if (seed && !WHOLE.test(seed)) throw new Error(`QA_PROBES_SEED «${seed}» is not a whole number.`);
  return { size: Number(size), seed: seed ? Number(seed) : 1 };
}

const keysOf = (probe: Probe): string[] => DIMENSIONS.map((dimension) => `${dimension}:${probe[dimension]}`);

interface Pile {
  keys: string[];
  probes: Probe[];
}

/** The probes grouped by app, role, language and expectation: the groups and each one's probes in the draw's order. */
function piles(probes: Probe[], next: () => number): Pile[] {
  const grouped = new Map<string, Probe[]>();
  for (const probe of [...probes].sort((a, b) => a.id.localeCompare(b.id))) {
    const key = keysOf(probe).join('|');
    grouped.set(key, [...(grouped.get(key) ?? []), probe]);
  }
  const ordered = [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  return shuffled(ordered, next).map(([, group]) => ({ keys: keysOf(group[0]), probes: shuffled(group, next) }));
}

/** The group whose app, role, language and expectation have given the least of their share so far (the first on a tie). */
function leastTaken(groups: Pile[], taken: Map<string, number>, share: Map<string, number>): Pile {
  let best = groups[0];
  let lowest = Number.POSITIVE_INFINITY;
  for (const group of groups) {
    if (!group.probes.length) continue;
    const score = group.keys.reduce((sum, key) => sum + (taken.get(key) ?? 0) / (share.get(key) ?? 1), 0);
    if (score < lowest) [best, lowest] = [group, score];
  }
  return best;
}

/** `choice.size` probes of `probes`, in the corpus' order; all of them when the sample is not smaller. */
export function sampleProbes(probes: Probe[], choice: SampleChoice): Probe[] {
  if (choice.size >= probes.length) return [...probes];
  const share = new Map<string, number>();
  for (const key of probes.flatMap(keysOf)) share.set(key, (share.get(key) ?? 0) + 1);
  const groups = piles(probes, random(choice.seed));
  const taken = new Map<string, number>();
  const chosen = new Set<string>();
  while (chosen.size < choice.size) {
    const probe = leastTaken(groups, taken, share).probes.shift() as Probe;
    chosen.add(probe.id);
    for (const key of keysOf(probe)) taken.set(key, (taken.get(key) ?? 0) + 1);
  }
  return probes.filter((probe) => chosen.has(probe.id));
}
