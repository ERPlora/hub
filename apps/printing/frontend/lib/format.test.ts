// What the printing screens paint from the server's rows: how long a job has waited («3 min»), a job's
// name («Receipt T-000123», or «Receipt · 14/10/26, 23:05» without a number), its detail line, a printer's
// address and paper, and the tone of each status.
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { JobOut, PrinterOut } from '../operations';
import { JOB_TONE, jobDetail, jobFlags, jobTitle, printerAddress, printerPaper, printerState, STATE_TONE, waited } from './format';

const i18n = createShellI18n({ locale: 'en', messages: { en, es } });
const t = (key: string, named?: Record<string, unknown>) => (named ? i18n.global.t(key, named) : i18n.global.t(key));

const NOW = new Date('2026-10-14T21:10:00Z');

const job = (more: Partial<JobOut> = {}): JobOut =>
  ({
    id: 'j1',
    kind: 'document',
    document_type: 'receipt',
    reference: 'T-000123',
    status: 'pending',
    leased_until: null,
    last_error: '',
    retried_by: '',
    cancelled_by: '',
    cancel_reason: '',
    created_at: '2026-10-14T21:05:00Z',
    ...more,
  }) as JobOut;

const printer = (more: Partial<PrinterOut> = {}): PrinterOut =>
  ({ kind: 'network', address: '192.168.1.50', port: 9100, paper_width: 80, ...more }) as PrinterOut;

describe('waited', () => {
  it('says seconds, minutes or hours, rounded down', () => {
    expect(waited('2026-10-14T21:09:35Z', NOW, t)).toBe('25\u00a0s');
    expect(waited('2026-10-14T21:07:00Z', NOW, t)).toBe('3\u00a0min');
    expect(waited('2026-10-14T18:00:00Z', NOW, t)).toBe('3\u00a0h');
    expect(waited('2026-10-14T21:11:00Z', NOW, t)).toBe('0\u00a0s');
  });

  it('keeps the number with its unit: a narrow card never breaks «0» from «s»', () => {
    const inSpanish = (key: string, named?: Record<string, unknown>) => i18n.global.t(key, named ?? {}, { locale: 'es' });
    for (const [translate, from] of [
      [t, '2026-10-14T21:09:35Z'],
      [t, '2026-10-14T21:07:00Z'],
      [t, '2026-10-14T18:00:00Z'],
      [inSpanish, '2026-10-14T21:09:35Z'],
      [inSpanish, '2026-10-14T21:07:00Z'],
      [inSpanish, '2026-10-14T18:00:00Z'],
    ] as const) {
      const age = waited(from, NOW, translate);
      expect(age, age).toMatch(/^\d+ (s|min|h)$/);
    }
  });
});

describe('jobTitle', () => {
  it('names a job by its document and its number', () => {
    expect(jobTitle(job(), t, 'en')).toBe('Receipt T-000123');
    expect(jobTitle(job({ document_type: 'kitchen_order', reference: '42' }), t, 'en')).toBe('Kitchen order 42');
  });

  it('a test page and the drawer are named by what they are', () => {
    expect(jobTitle(job({ kind: 'test_page', document_type: '', reference: 'Kitchen' }), t, 'en')).toBe('Test page Kitchen');
    expect(jobTitle(job({ kind: 'drawer', document_type: '', reference: 'T-1' }), t, 'en')).toBe('Open the drawer T-1');
  });

  it('without a number, by when it was asked for', () => {
    expect(jobTitle(job({ reference: '' }), t, 'en')).toMatch(/^Receipt · /);
  });
});

describe('jobDetail', () => {
  it('says why a job is where it is', () => {
    expect(jobDetail(job(), t, NOW)).toBe('');
    expect(jobDetail(job({ status: 'failed', last_error: 'out of paper' }), t, NOW)).toBe('Last error: out of paper');
    expect(jobDetail(job({ status: 'sent', leased_until: '2026-10-14T21:09:00Z' }), t, NOW)).toBe('No answer from the device');
    expect(jobDetail(job({ status: 'cancelled', cancelled_by: 'Ana', cancel_reason: 'left' }), t, NOW)).toBe('Cancelled by Ana · Reason: left');
    expect(jobDetail(job({ status: 'cancelled', cancelled_by: 'Ana' }), t, NOW)).toBe('Cancelled by Ana');
    expect(jobDetail(job({ status: 'pending', retried_by: 'Ana', last_error: 'jam' }), t, NOW)).toBe('Sent again by Ana · Last error: jam');
  });
});

describe('jobFlags', () => {
  it('reads from the clock whether a sent job is still the device’s', () => {
    const sent = job({ status: 'sent', leased_until: '2026-10-14T21:10:30Z' });
    expect(jobFlags(sent, NOW)).toEqual({ stale: false, retryable: false, cancellable: false });
    expect(jobFlags(sent, new Date('2026-10-14T21:11:00Z'))).toEqual({ stale: true, retryable: true, cancellable: true });
  });

  it('a queued or failed job is retried and cancelled; a printed or cancelled one, neither', () => {
    expect(jobFlags(job({ status: 'pending' }), NOW)).toEqual({ stale: false, retryable: true, cancellable: true });
    expect(jobFlags(job({ status: 'failed' }), NOW)).toEqual({ stale: false, retryable: true, cancellable: true });
    expect(jobFlags(job({ status: 'done' }), NOW)).toEqual({ stale: false, retryable: false, cancellable: false });
    expect(jobFlags(job({ status: 'cancelled' }), NOW)).toEqual({ stale: false, retryable: false, cancellable: false });
  });
});

describe('printerState', () => {
  it('waits once its oldest job has waited over a minute, by the clock', () => {
    const queued = printer({ is_active: true, last_printed_at: null, last_failed_at: null, oldest_pending_at: '2026-10-14T21:09:30Z' });
    expect(printerState(queued, NOW)).toBe('ready');
    expect(printerState(queued, new Date('2026-10-14T21:10:31Z'))).toBe('waiting');
  });

  it('is inactive, or failing while its last failure is newer than its last paper', () => {
    expect(printerState(printer({ is_active: false }), NOW)).toBe('inactive');
    const failing = printer({ is_active: true, last_failed_at: '2026-10-14T21:00:00Z', last_printed_at: '2026-10-14T20:00:00Z', oldest_pending_at: null });
    expect(printerState(failing, NOW)).toBe('failing');
    expect(printerState({ ...failing, last_printed_at: '2026-10-14T21:05:00Z' }, NOW)).toBe('ready');
  });
});

describe('a printer', () => {
  it('shows its address as the app reaches it', () => {
    expect(printerAddress(printer())).toBe('192.168.1.50:9100');
    expect(printerAddress(printer({ kind: 'bluetooth', address: 'AA:BB:CC:DD:EE:FF', port: null }))).toBe('AA:BB:CC:DD:EE:FF');
    expect(printerAddress(printer({ kind: 'system', address: '', port: null }))).toBe('—');
  });

  it('shows its paper', () => {
    expect(printerPaper(printer(), t)).toBe('80 mm');
    expect(printerPaper(printer({ paper_width: 58 }), t)).toBe('58 mm');
    expect(printerPaper(printer({ kind: 'system' }), t)).toBe('A4');
  });
});

describe('tones', () => {
  it('give each state and status its colour', () => {
    expect(STATE_TONE).toEqual({ ready: 'success', waiting: 'warning', failing: 'danger', inactive: 'neutral' });
    expect(JOB_TONE).toEqual({ pending: 'warning', sent: 'info', done: 'success', failed: 'danger', cancelled: 'neutral' });
  });
});
