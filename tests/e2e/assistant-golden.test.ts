// @vitest-environment node
// A scenario's golden path and setup: the tool calls a perfect assistant would make, run in the business by the Hub's own
// tool path as its owner with no model, in batches whose later steps take values from the results of earlier ones.
import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { GOLDEN_PY, goldenCommand, parseStepResults, resolved, runSteps, type StepRun } from './assistant-golden';
import type { ToolStep } from './assistant-scenario';

const ok = (content: unknown): StepRun => ({ tool: '', outcome: 'ok', code: '', content: JSON.stringify(content), card: false });

describe('resolved', () => {
  const results = { cats: { rows: [{ id: 'c1', name: 'Bebidas' }, { id: 'c2', name: 'Cafés' }] }, sale: { id: 's1', lines: [{ id: 'l1', product_name: 'Agua mineral' }] } };

  it('writes into a step the values of earlier results it names by their fields', () => {
    const args = { category_ids: [{ $ref: 'cats', where: { name: 'bebidas' }, take: 'id' }], sale_id: { $ref: 'sale', take: 'id' }, lines: [{ line_id: { $ref: 'sale', where: { product_name: 'Agua mineral' }, take: 'id' } }] };
    expect(resolved(args, results)).toEqual({ category_ids: ['c1'], sale_id: 's1', lines: [{ line_id: 'l1' }] });
  });

  it('stops on a value it cannot find, naming the step and what it looked for', () => {
    expect(() => resolved({ x: { $ref: 'cats', where: { name: 'Vinos' }, take: 'id' } }, results)).toThrow(/cats has no .*Vinos/);
    expect(() => resolved({ x: { $ref: 'nope', take: 'id' } }, results)).toThrow(/no step nope/);
  });
});

describe('runSteps', () => {
  const steps: ToolStep[] = [
    { id: 'cats', tool: 'inventory.category.list', arguments: {} },
    { tool: 'tax.category.list', arguments: { search: 'comida' } },
    { tool: 'inventory.product.update', arguments: { product: 'BEB-01', category_ids: [{ $ref: 'cats', where: { name: 'Bebidas' }, take: 'id' }] } },
  ];

  it('runs consecutive steps together until one needs an earlier result, then the rest with it written in', () => {
    const batches: ToolStep[][] = [];
    const run = runSteps(steps, (batch) => {
      batches.push(batch);
      return batch.map((step) => ({ ...ok(step.id === 'cats' ? { rows: [{ id: 'c1', name: 'Bebidas' }] } : {}), tool: step.tool }));
    });
    expect(batches.map((batch) => batch.map((step) => step.tool))).toEqual([['inventory.category.list', 'tax.category.list'], ['inventory.product.update']]);
    expect(batches[1][0].arguments).toEqual({ product: 'BEB-01', category_ids: ['c1'] });
    expect(run.failed).toBeNull();
    expect(run.results).toHaveLength(3);
  });

  it('stops at the first step that did not run, saying which and why', () => {
    const run = runSteps(steps, (batch) => batch.map((step, index) => (index === 1 ? { tool: step.tool, outcome: 'error', code: 'invalid_payload', content: '{"error":{"message":"bad"}}', card: false } : { ...ok({}), tool: step.tool })));
    expect(run.failed).toEqual({ step: 2, tool: 'tax.category.list', why: 'error invalid_payload: {"error":{"message":"bad"}}' });
    expect(run.results).toHaveLength(2);
  });

  it('stops when a value cannot be written in, before running its batch', () => {
    const run = runSteps(steps, (batch) => batch.map((step) => ({ ...ok({ rows: [] }), tool: step.tool })));
    expect(run.failed?.step).toBe(3);
    expect(run.failed?.why).toMatch(/cats has no/);
  });
});

describe('goldenCommand and GOLDEN_PY', () => {
  it('runs a batch in the business as its owner: the setup by the tool runner, the golden path through the assistant\'s turn', () => {
    const command = goldenCommand({ file: '/tmp/steps.json', mode: 'golden', language: 'es' }, { PATH: '/bin', GONE: undefined });
    expect(command).toEqual({
      file: 'uv',
      args: ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', GOLDEN_PY],
      env: { PATH: '/bin', QA_GOLDEN_FILE: '/tmp/steps.json', QA_GOLDEN_MODE: 'golden', QA_GOLDEN_LANGUAGE: 'es' },
    });
    expect(GOLDEN_PY).toContain('get_operation("base.assistant.turn")');
    expect(GOLDEN_PY).toContain('shared.run_tool(ctx, get_operation(step["tool"])');
    expect(GOLDEN_PY).toContain('"accepted": True');
    expect(GOLDEN_PY).toContain('confirm_word');
    const parsed = spawnSync('python3', ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: GOLDEN_PY, encoding: 'utf8' });
    expect(parsed.status, parsed.stderr).toBe(0);
  });

  it('reads what each step answered from the shell\'s last line', () => {
    expect(parseStepResults('9 objects imported\n[{"tool": "a.b.c", "outcome": "ok", "code": "", "content": "{}", "card": true}]')).toEqual([{ tool: 'a.b.c', outcome: 'ok', code: '', content: '{}', card: true }]);
    expect(() => parseStepResults('Traceback: boom')).toThrow(/did not answer/);
  });
});
