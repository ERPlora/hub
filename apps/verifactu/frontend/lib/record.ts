// What the VeriFactu screens say about a record, the same in the list, the detail and the queue: the closed lists
// the server knows (apps/verifactu/models.py) and the tone of a status, an environment and a severity.
import type { StatusPillTone } from '@erplora/ui/components';

import type { Environment, EventKind, InvoiceType, RecordStatus, RecordType, Severity } from '../operations';

export const STATUSES: readonly RecordStatus[] = ['pending', 'sent', 'accepted', 'accepted_with_errors', 'rejected'];
export const RECORD_TYPES: readonly RecordType[] = ['alta', 'anulacion'];
export const ENVIRONMENTS: readonly Environment[] = ['testing', 'production'];
export const INVOICE_TYPES: readonly InvoiceType[] = ['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5'];
export const SEVERITIES: readonly Severity[] = ['debug', 'info', 'warning', 'error', 'critical'];
export const EVENT_KINDS: readonly EventKind[] = [
  'record_created',
  'deferred',
  'accepted',
  'accepted_with_errors',
  'failed',
  'queue_processed',
  'queue_retried',
  'chain_valid',
  'chain_broken',
  'aeat_queried',
  'chain_recovered',
  'connection_test',
  'config_changed',
];

const STATUS_TONES: Record<RecordStatus, StatusPillTone> = {
  pending: 'warning',
  sent: 'info',
  accepted: 'success',
  accepted_with_errors: 'warning',
  rejected: 'danger',
};
const SEVERITY_TONES: Record<Severity, StatusPillTone> = {
  debug: 'neutral',
  info: 'info',
  warning: 'warning',
  error: 'danger',
  critical: 'danger',
};

/** Green in the AEAT, amber waiting (or with errors), red rejected. */
export function statusTone(status: RecordStatus): StatusPillTone {
  return STATUS_TONES[status] ?? 'neutral';
}

/** Production is what counts before the tax agency: it stands out. */
export function environmentTone(environment: Environment): StatusPillTone {
  return environment === 'production' ? 'success' : 'neutral';
}

export function severityTone(severity: Severity): StatusPillTone {
  return SEVERITY_TONES[severity] ?? 'neutral';
}

/** A fingerprint cut for a table (its head and its tail); nothing is «—». */
export function short(fingerprint: string): string {
  if (!fingerprint) return '—';
  return fingerprint.length > 24 ? `${fingerprint.slice(0, 10)}…${fingerprint.slice(-10)}` : fingerprint;
}
