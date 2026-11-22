// @vitest-environment node
// Whether a scenario can be asked at all, by rules that are the same for every model: whether the model sees the photo
// it attaches. The tools its opening is offered never stop it, since the assistant searches for the one it lacks.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { notRunnable, SENT_SQL } from './assistant-precheck';
import { parseScenario, type Scenario } from './assistant-scenario';

const CORPUS = join(dirname(fileURLToPath(import.meta.url)), 'qa', 'scenarios');
const corpus = (id: string): Scenario => parseScenario(readFileSync(join(CORPUS, `${id}.json`), 'utf8'), `${id}.json`);

describe('notRunnable', () => {
  const scenario = (attachments: unknown[]) => ({ attachments }) as unknown as Scenario;
  const xlsx = { kind: 'xlsx', name: 'carta.xlsx', sheet: 'Carta', rows: [['a']] };
  const picture = { kind: 'photo', name: 'albaran.jpg', note: {} };

  it('asks a scenario without a photo of any model, with files or without', () => {
    expect(notRunnable(scenario([xlsx]), false)).toBeNull();
    expect(notRunnable(scenario([]), false)).toBeNull();
  });

  it('asks s05 and s06, whose openings were not offered a tool of the job: the assistant searches for the one it lacks', () => {
    expect(notRunnable(corpus('s05-raise-drinks'), true)).toBeNull();
    expect(notRunnable(corpus('s06-breakage-and-count'), true)).toBeNull();
  });

  it('does not ask one with a photo when the model does not see images', () => {
    expect(notRunnable(scenario([picture]), false)).toBe('not runnable: the model does not see images');
    expect(notRunnable(scenario([picture]), true)).toBeNull();
  });
});

describe('SENT_SQL', () => {
  it('counts every fiscal record that left the business or is no longer waiting locally', () => {
    expect(SENT_SQL).toContain('from verifactu_record');
    expect(SENT_SQL).toContain('transmitted_at is not null');
    expect(SENT_SQL).not.toMatch(/["$`]/);
  });
});
