// hub#845 — «retry ONLY what did not make it in», derived from the persisted import report.
//
// The recovered report in Settings › Data (hub#763) offers one retry button. Whether it can act is
// a property OF THE REPORT, computed here so the panel stays declarative and the rule is testable
// without a browser:
//   - something must actually have failed, or stayed `blocked` on a purchase (ADR-0060: after
//     subscribing, the SAME button re-runs it);
//   - the import must have a catalogue origin (slug + version) the hub can re-download. A local
//     upload has none — the button says WHY it cannot act instead of hiding (the server refuses it
//     too; this is the honest disable, not the enforcement).
//
// Uses the SAME status normalisers the panel paints with (real collaborators, lesson hub#770), so
// «what looks failed on screen» and «what the retry would re-run» cannot drift apart.

import {
  moduleInstallStatusInfo,
  sectionStatusInfo,
  type ImportReport,
} from './runtime';

/** Why the retry button cannot act (`null` when it can). */
export type RetryReason = 'not_retryable_origin' | 'nothing_to_retry';

export interface RetryAvailability {
  canRetry: boolean;
  reason: RetryReason | null;
}

/**
 * `true` when the report holds something a retry would actually re-run: a `Failed` section, a
 * module in `failed`/`blocked`, or media files that could not be copied. `Ignored` and
 * `PartiallyApplied` are the engine's own decisions — retrying them repeats the same discard, so
 * they do not count.
 */
export function hasRetryableTrouble(report: ImportReport): boolean {
  const sectionFailed = (report.sections ?? []).some(
    (s) => sectionStatusInfo(s.status).kind === 'failed',
  );
  const moduleTrouble = (report.installed_modules ?? []).some((m) => {
    const kind = moduleInstallStatusInfo(m).kind;
    return kind === 'failed' || kind === 'blocked';
  });
  const mediaFailed = Boolean(report.media?.selected) && (report.media?.failed ?? 0) > 0;
  return sectionFailed || moduleTrouble || mediaFailed;
}

/**
 * Whether «Retry what's missing» can act on this report, and why not when it cannot.
 *
 * The order matters: a fully applied import is «nothing to retry» even when its origin is the
 * catalogue — offering a retry that would be a no-op teaches the user the button does nothing.
 */
export function retryAvailability(report: ImportReport): RetryAvailability {
  if (!hasRetryableTrouble(report)) {
    return { canRetry: false, reason: 'nothing_to_retry' };
  }
  const origin = report.origin;
  if (origin?.source !== 'catalog' || !origin.slug || !origin.version) {
    // No origin (local upload, or a report older than the field): the hub cannot guarantee it
    // would re-download the SAME bundle, so it does not try (hub#845).
    return { canRetry: false, reason: 'not_retryable_origin' };
  }
  return { canRetry: true, reason: null };
}

/**
 * i18n key for a stable retry error code from the server (ADR-0205 lesson: codes travel, the shell
 * translates). `null` → unknown code or prose: show the server's honest message as-is.
 */
export function retryErrorKey(code: string | undefined): string | null {
  switch (code) {
    case 'import_origin_not_retryable':
      return 'importPage.retryNotRetryable';
    case 'import_retry_version_unavailable':
      return 'importPage.retryVersionUnavailable';
    case 'import_retry_batch_not_found':
      return 'importPage.retryBatchNotFound';
    default:
      return null;
  }
}
