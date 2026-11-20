// @vitest-environment node
// The sample of the corpus a run asks (QA_PROBES_SAMPLE, QA_PROBES_SEED): the same phrases for the same seed, so every
// model answers the same ones, spread across the apps, roles, languages and expectations of the corpus.
import { describe, expect, it } from 'vitest';

import type { Expect, Probe, Role } from './assistant-probes';
import { sampleChoice, sampleProbes } from './assistant-sample';

const EXPECTS: Expect[] = ['read', 'card', 'refused', 'docs'];

/** `count` probes: apps a0..a5, owner nine times in ten, Spanish but every tenth, the four expectations in turn. */
function corpus(count: number): Probe[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `p${String(index).padStart(3, '0')}`,
    app: `a${index % 6}`,
    tool: `a${index % 6}.thing.act`,
    role: (index % 10 === 3 ? 'employee' : 'owner') as Role,
    language: index % 10 === 7 ? 'en' : 'es',
    phrase: `phrase ${index}`,
    expect: EXPECTS[index % 4],
  }));
}

const ids = (probes: Probe[]) => probes.map((probe) => probe.id);
const values = (probes: Probe[], key: keyof Probe) => new Set(probes.map((probe) => String(probe[key])));

describe('sampleChoice', () => {
  it('asks no sample by default', () => {
    expect(sampleChoice({})).toBeNull();
  });

  it('reads the size and the seed, the seed 1 when none is given', () => {
    expect(sampleChoice({ QA_PROBES_SAMPLE: '150', QA_PROBES_SEED: '42' })).toEqual({ size: 150, seed: 42 });
    expect(sampleChoice({ QA_PROBES_SAMPLE: '10' })).toEqual({ size: 10, seed: 1 });
  });

  it('refuses a size or a seed that is not a whole number, and a seed without a size', () => {
    expect(() => sampleChoice({ QA_PROBES_SAMPLE: 'many' })).toThrow(/QA_PROBES_SAMPLE/);
    expect(() => sampleChoice({ QA_PROBES_SAMPLE: '0' })).toThrow(/QA_PROBES_SAMPLE/);
    expect(() => sampleChoice({ QA_PROBES_SAMPLE: '5', QA_PROBES_SEED: '1.5' })).toThrow(/QA_PROBES_SEED/);
    expect(() => sampleChoice({ QA_PROBES_SEED: '3' })).toThrow(/QA_PROBES_SAMPLE/);
  });
});

describe('sampleProbes', () => {
  const all = corpus(200);

  it('draws the same probes for the same seed, whatever order the corpus came in', () => {
    const drawn = ids(sampleProbes(all, { size: 30, seed: 9 }));
    expect(drawn).toHaveLength(30);
    expect(ids(sampleProbes([...all].reverse(), { size: 30, seed: 9 })).sort()).toEqual([...drawn].sort());
    expect(ids(sampleProbes(all, { size: 30, seed: 10 }))).not.toEqual(drawn);
  });

  it('keeps the corpus order and asks the whole corpus when the sample is not smaller', () => {
    const drawn = sampleProbes(all, { size: 30, seed: 9 });
    expect(ids(drawn)).toEqual([...ids(drawn)].sort());
    expect(sampleProbes(all, { size: 500, seed: 9 })).toEqual(all);
  });

  it('reaches every app, role, language and expectation even in a small sample', () => {
    const drawn = sampleProbes(all, { size: 8, seed: 3 });
    for (const key of ['app', 'role', 'language', 'expect'] as const) expect(values(drawn, key)).toEqual(values(all, key));
  });

  it('keeps each one near its share of the corpus in a larger sample', () => {
    const drawn = sampleProbes(all, { size: 100, seed: 5 });
    const owners = drawn.filter((probe) => probe.role === 'owner').length;
    const spanish = drawn.filter((probe) => probe.language === 'es').length;
    expect(owners).toBeGreaterThanOrEqual(85);
    expect(owners).toBeLessThanOrEqual(92);
    expect(spanish).toBeGreaterThanOrEqual(85);
    expect(spanish).toBeLessThanOrEqual(92);
    for (const expectation of EXPECTS) expect(drawn.filter((probe) => probe.expect === expectation).length).toBe(25);
  });
});
