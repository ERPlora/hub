// @vitest-environment node
// The records a sampled run of the probes needs before its first probe (`qa/setup.json`), made in `a` by the Hub's own
// tools with fixed data and no model, and the rule that leaves out of the score a probe whose record the setup cannot
// make. The setup itself only runs with QA_REAL_PROVIDER=1.
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import type { Probe } from './assistant-probes';
import {
  isPreparation,
  madridToday,
  missingFor,
  namesOf,
  parseSetup,
  parseSetupRun,
  SETUP_PY,
  setupCommand,
  settled,
  withDates,
} from './assistant-setup';

const probe = (tool: string, phrase: string): Probe => ({ id: 'p', app: tool.split('.')[0], tool, role: 'owner', language: 'es', phrase, expect: 'card' });

describe('parseSetup', () => {
  it('reads the steps of the setup: a tool, its arguments and the names it makes', () => {
    const text = JSON.stringify({ steps: [{ tool: 'table.zone.create', arguments: { name: 'Comedor QA' }, provides: ['Comedor QA'] }] });
    expect(parseSetup(text, 'setup.json')).toEqual([{ tool: 'table.zone.create', arguments: { name: 'Comedor QA' }, provides: ['Comedor QA'] }]);
  });

  it('refuses a step that is not a tool with its arguments and names, naming the step', () => {
    expect(() => parseSetup('{"steps": [{"tool": "zone", "arguments": {}, "provides": []}]}', 'setup.json')).toThrow(/setup.json: step 1/);
    expect(() => parseSetup('{"steps": [{"tool": "a.b.c", "arguments": [], "provides": []}]}', 'setup.json')).toThrow(/arguments/);
    expect(() => parseSetup('{"steps": [{"tool": "a.b.c", "arguments": {}, "provides": "x"}]}', 'setup.json')).toThrow(/provides/);
    expect(() => parseSetup('[]', 'setup.json')).toThrow(/steps/);
  });

  it('is the corpus setup, whose steps all parse', () => {
    const steps = parseSetup(readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'qa', 'setup.json'), 'utf8'), 'qa/setup.json');
    expect(steps.length).toBeGreaterThan(20);
  });
});

describe('withDates', () => {
  it('writes the day of the run into every text that asks for it', () => {
    const [step] = withDates([{ tool: 'a.b.c', arguments: { date: '{today+1}', at: '{today}T21:00', list: [{ day: '{today-2}' }], year: '{year}', n: 2 }, provides: [] }], '2026-12-31');
    expect(step.arguments).toEqual({ date: '2027-01-01', at: '2026-12-31T21:00', list: [{ day: '2026-12-29' }], year: 2026, n: 2 });
  });

  it('takes the day in Madrid, where the business is', () => {
    expect(madridToday(new Date('2026-11-19T23:30:00Z'))).toBe('2026-11-20');
    expect(madridToday(new Date('2026-11-19T10:00:00Z'))).toBe('2026-11-19');
  });
});

describe('settled', () => {
  const steps = [
    { tool: 'table.zone.create', arguments: {}, provides: ['Comedor QA'] },
    { tool: 'staff.member.create', arguments: {}, provides: ['Fichaje QA'] },
    { tool: 'customer.customer.create', arguments: {}, provides: ['Ana QA'] },
  ];

  it('counts a name only when its step ran and its result names it', () => {
    const run = settled(steps, [
      { outcome: 'ok', code: '', content: '{"name": "Comedor QA"}' },
      { outcome: 'error', code: 'staff.role_not_found', content: '{"error": {}}' },
      { outcome: 'ok', code: '', content: '{"name": "Ana"}' },
    ]);
    expect(run.provided).toEqual({ 'table.zone': ['Comedor QA'] });
    expect(run.failed).toEqual([
      { step: 2, tool: 'staff.member.create', why: 'error staff.role_not_found' },
      { step: 3, tool: 'customer.customer.create', why: 'its result does not name Ana QA' },
    ]);
  });

  it('refuses a run that did not answer every step', () => {
    expect(() => settled(steps, [])).toThrow(/3 steps, 0 results/);
  });
});

describe('namesOf', () => {
  it('finds the records a phrase names: names ending in QA, QA codes and dated numbers', () => {
    expect(namesOf('guarda la mesa 5 de Comedor QA para Ana QA mañana, con referencia QA-HOLD-2')).toEqual(['Comedor QA', 'Ana QA', 'QA-HOLD-2']);
    expect(namesOf('el pedido OS-20261109-0001 y la venta 20261109-0001 de product.qa')).toEqual(['OS-20261109-0001', '20261109-0001', 'product.qa']);
    expect(namesOf('el Café de Mayorista QA y el Bono QA de Ana QA en la Cuenta bonos QA')).toEqual(['Mayorista QA', 'Bono QA', 'Ana QA', 'Cuenta bonos QA']);
  });

  it('leaves out what is quoted, a new value rather than a record, and the SKU word before a code', () => {
    expect(namesOf('renombra Sin azúcar QA como «Sin azúcar ni edulcorante QA»')).toEqual(['Sin azúcar QA']);
    expect(namesOf('crea Merluza con SKU QA-MERLUZA')).toEqual(['QA-MERLUZA']);
  });
});

describe('missingFor', () => {
  const run = { provided: { 'table.zone': ['Comedor QA'], 'service.category': ['Peluquería QA'] }, failed: [] };

  it('scores a probe whose records the setup made, and one that names none', () => {
    expect(missingFor(probe('table.table.get', '¿cómo está la mesa 1 de Comedor QA?'), run)).toEqual([]);
    expect(missingFor(probe('sale.sale.today', '¿cuánto llevo hoy?'), run)).toEqual([]);
  });

  it('leaves out a probe that names a record the setup does not make', () => {
    expect(missingFor(probe('attendance.record.clock_in', 'ficha la entrada de Fichaje QA'), run)).toEqual([
      'it names «Fichaje QA», which the setup does not make',
    ]);
  });

  it('scores a create of a new record, and leaves out one of a record the setup already made', () => {
    expect(missingFor(probe('table.table.bulk_create', 'crea en Comedor QA seis mesas'), run)).toEqual([]);
    expect(missingFor(probe('service.category.create', 'crea la categoría Masaje QA'), run)).toEqual([]);
    expect(missingFor(probe('table.hold.place', 'guarda la mesa 5 de Comedor QA con referencia QA-HOLD-2'), run)).toEqual([]);
    expect(missingFor(probe('service.category.create', 'crea la categoría Peluquería QA'), run)).toEqual([
      'the setup already made «Peluquería QA» with service.category',
    ]);
  });
});

describe('isPreparation', () => {
  it('tells the corpus files that only prepare the business from the probes', () => {
    expect(isPreparation('tests/e2e/qa/probes/owner-es-preparation-sales-2026-11-09.json')).toBe(true);
    expect(isPreparation('/x/owner-es-preparation-2026-11-09.json')).toBe(true);
    expect(isPreparation('tests/e2e/qa/probes/owner-es-table-2026-11-08.json')).toBe(false);
  });
});

describe('the setup command', () => {
  it('runs in a as its owner with the steps in a file, never in the arguments', () => {
    const command = setupCommand('/tmp/setup.json', { PATH: '/bin' });
    expect(command).toEqual({
      file: 'uv',
      args: ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', SETUP_PY],
      env: { PATH: '/bin', QA_SETUP_FILE: '/tmp/setup.json' },
    });
  });

  it('runs every step through the tool runner of the assistant, as the owner, and is Python', () => {
    expect(SETUP_PY).toContain('shared.run_tool(ctx, get(step["tool"]), json.dumps(step["arguments"]))');
    expect(SETUP_PY).toContain('permissions_for(owner, scope)');
    const parsed = spawnSync('python3', ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: SETUP_PY, encoding: 'utf8' });
    expect(parsed.status, parsed.stderr).toBe(0);
  });

  it('reads the results the shell printed on its last line', () => {
    expect(parseSetupRun('3 objects imported\n[{"outcome": "ok", "code": "", "content": "{}"}]\n')).toEqual([{ outcome: 'ok', code: '', content: '{}' }]);
  });
});
