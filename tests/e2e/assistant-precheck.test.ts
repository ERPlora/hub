// @vitest-environment node
// Whether a scenario can be asked at all, by rules that are the same for every model: the tools the turn offers its
// attached opening message (a message with files that is not offered the job's tools cannot pass with any model), and
// whether the model sees the photo it attaches.
import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { notRunnable, OFFERED_TURN_PY, offeredTurnCommand, openingContent, parseOfferedTurn, SENT_SQL } from './assistant-precheck';
import type { Scenario } from './assistant-scenario';

const sheet = { name: 'carta.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('PK..') };
const photo = { name: 'albaran.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('jpg') };

describe('openingContent', () => {
  it('is the text alone without files, as the chat sends it', () => {
    expect(openingContent('hola', [])).toBe('hola');
  });

  it('is the text and each file as a part, as the chat sends them: a document as a file, an image as its data address', () => {
    expect(openingContent('mete esto', [sheet, photo])).toEqual([
      { type: 'text', text: 'mete esto' },
      { type: 'input_file', filename: 'carta.xlsx', mime_type: sheet.mimeType, data: Buffer.from('PK..').toString('base64') },
      { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${Buffer.from('jpg').toString('base64')}` } },
    ]);
  });
});

describe('notRunnable', () => {
  const scenario = (attachments: unknown[], offered: string[]) => ({ attachments, offered }) as unknown as Scenario;
  const xlsx = { kind: 'xlsx', name: 'carta.xlsx', sheet: 'Carta', rows: [['a']] };
  const picture = { kind: 'photo', name: 'albaran.jpg', note: {} };

  it('asks a scenario whose opening is offered every tool it needs, or that names none', () => {
    expect(notRunnable(scenario([xlsx], ['inventory.product.bulk_create']), ['base.setup.status', 'inventory.product.bulk_create'], false)).toBeNull();
    expect(notRunnable(scenario([], []), null, false)).toBeNull();
  });

  it('does not ask one whose attached message misses a tool the job needs, naming them', () => {
    expect(notRunnable(scenario([xlsx], ['inventory.product.bulk_create', 'inventory.category.list']), ['inventory.category.list'], true)).toBe(
      'not runnable: tools not offered on the attached message (inventory.product.bulk_create)',
    );
  });

  it('does not ask one whose opening, without files, misses a tool the job needs', () => {
    expect(notRunnable(scenario([], ['inventory.product.list', 'inventory.product.update']), ['inventory.product.update'], false)).toBe(
      'not runnable: tools not offered on the opening message (inventory.product.list)',
    );
  });

  it('does not ask one with a photo when the model does not see images', () => {
    expect(notRunnable(scenario([picture], []), [], false)).toBe('not runnable: the model does not see images');
    expect(notRunnable(scenario([picture], []), [], true)).toBeNull();
  });
});

describe('OFFERED_TURN_PY', () => {
  it('asks the assistant\'s own turn which tools it offers the opening message, as the owner', () => {
    expect(offeredTurnCommand({ file: '/tmp/opening.json', language: 'es' }, { PATH: '/bin' })).toEqual({
      file: 'uv',
      args: ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', OFFERED_TURN_PY],
      env: { PATH: '/bin', QA_OPENING_FILE: '/tmp/opening.json', QA_OPENING_LANGUAGE: 'es' },
    });
    expect(OFFERED_TURN_PY).toContain('get_operation("base.assistant.turn")');
    const parsed = spawnSync('python3', ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: OFFERED_TURN_PY, encoding: 'utf8' });
    expect(parsed.status, parsed.stderr).toBe(0);
  });

  it('reads the offered tools by their operation names', () => {
    expect(parseOfferedTurn('5 objects\n["base__setup__status", "inventory__product__bulk_create"]')).toEqual(['base.setup.status', 'inventory.product.bulk_create']);
  });
});

describe('SENT_SQL', () => {
  it('counts every fiscal record that left the business or is no longer waiting locally', () => {
    expect(SENT_SQL).toContain('from verifactu_record');
    expect(SENT_SQL).toContain('transmitted_at is not null');
    expect(SENT_SQL).not.toMatch(/["$`]/);
  });
});
