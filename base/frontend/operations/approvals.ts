// Types of base/schemas/approvals.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.ApprovalOut`: one approval of the record (Employees › Approvals). */
export interface ApprovalRow {
  id: string;
  at: string;
  /** What was approved, in words, with the figures of what was done («Discount a line by 50 %»). */
  action: string;
  /** What the action is called, without figures: what the «Action» filter offers. */
  operation_label: string;
  operation: string;
  requested_by: string;
  approved_by: string;
  way: 'pin' | 'badge';
  used: boolean;
  used_at: string | null;
}

/** `base.ApprovalExportIn`: the search and the filters Employees › Approvals keeps on screen, as its table holds them
 *  (only the active ones; `used` is `'true'` or `'false'`). */
export interface ApprovalExportQuery {
  search?: string;
  at_from?: string;
  at_to?: string;
  operation?: string;
  way?: string;
  used?: string;
}

/** `base.ApprovalExportOut`: the CSV the server wrote. */
export interface ApprovalExport {
  filename: string;
  content_type: string;
  rows: number;
  csv: string;
}

/** `base.ApproverOut`: somebody who can approve the action, by name. */
export interface Approver {
  id: string;
  name: string;
  initials: string;
}

/** `base.ApprovalIn`: their person and PIN, or their badge. */
export interface ApprovalInput {
  operation: string;
  fingerprint: string;
  person?: string;
  pin?: string;
  badge?: string;
}

/** `base.ApprovalPassOut`: the pass of one use, and who approved. */
export interface ApprovalPass {
  token: string;
  approver: string;
  expires_in: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.approval.list': { input: NoInput; output: { approvals: ApprovalRow[] } };
    'base.approval.approvers': { input: { operation: string }; output: { people: Approver[]; pin_length: number } };
    'base.approval.export': { input: ApprovalExportQuery; output: ApprovalExport };
    'base.approval.approve': { input: ApprovalInput; output: ApprovalPass };
  }
}
