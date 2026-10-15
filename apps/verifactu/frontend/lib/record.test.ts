// What the VeriFactu screens say about a record: the closed lists the server knows, the tone of a status and of
// a severity, a fingerprint cut for a table and the verification link of the AEAT.
import { describe, expect, it } from 'vitest';

import {
  ENVIRONMENTS,
  EVENT_KINDS,
  INVOICE_TYPES,
  RECORD_TYPES,
  SEVERITIES,
  STATUSES,
  environmentTone,
  severityTone,
  short,
  statusTone,
} from './record';

describe('record helpers', () => {
  it('know the closed lists of the server (apps/verifactu/models.py)', () => {
    expect(STATUSES).toEqual(['pending', 'sent', 'accepted', 'accepted_with_errors', 'rejected']);
    expect(RECORD_TYPES).toEqual(['alta', 'anulacion']);
    expect(ENVIRONMENTS).toEqual(['testing', 'production']);
    expect(INVOICE_TYPES).toEqual(['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5']);
    expect(SEVERITIES).toEqual(['debug', 'info', 'warning', 'error', 'critical']);
    expect(EVENT_KINDS).toHaveLength(13);
  });

  it('colour a status: accepted green, waiting amber, rejected red', () => {
    expect(statusTone('accepted')).toBe('success');
    expect(statusTone('accepted_with_errors')).toBe('warning');
    expect(statusTone('pending')).toBe('warning');
    expect(statusTone('sent')).toBe('info');
    expect(statusTone('rejected')).toBe('danger');
  });

  it('colour the environment: production stands out', () => {
    expect(environmentTone('production')).toBe('success');
    expect(environmentTone('testing')).toBe('neutral');
  });

  it('colour a severity', () => {
    expect(severityTone('critical')).toBe('danger');
    expect(severityTone('error')).toBe('danger');
    expect(severityTone('warning')).toBe('warning');
    expect(severityTone('info')).toBe('info');
    expect(severityTone('debug')).toBe('neutral');
  });

  it('cut a fingerprint for a table, whole when short', () => {
    expect(short('A'.repeat(64))).toBe('AAAAAAAAAA…AAAAAAAAAA');
    expect(short('ABC')).toBe('ABC');
    expect(short('')).toBe('—');
  });
});
