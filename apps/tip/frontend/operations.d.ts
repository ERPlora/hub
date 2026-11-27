// Types of the tips app's operations the screens call, from apps/tip/schemas.py, for the SDK (`useLive`, `useCommand`,
// `client.api.call`). Written by hand, as the other apps' are: keep it in step with schemas.py and with
// `frontend/generated/operations.json`. Money is whole cents.

/** `SuggestedTipOut`: a suggestion as the tip it comes to on the charge's total. */
export interface SuggestedTip {
  /** The percentage it is; `null` when it is a fixed amount. */
  percent: number | null;
  amount: number;
}

/** `SuggestionOut`: what the charge proposes for a payment method. */
export interface SuggestionOut {
  enabled: boolean;
  allow_custom: boolean;
  /** Which suggestion comes chosen, 1 to 3; 0: «No tip». */
  preselected: number;
  /** None when tips are off. */
  suggestions: SuggestedTip[];
}

export interface SuggestionIn {
  method_id: string;
  /** The check's total before discounts, in cents. */
  total: number;
}

/** `TipAddIn`, as the charge sheet records the tip of a sale it charged. */
export interface TipAddIn {
  sale_id: string;
  method_id: string;
  amount: number;
  /** The charge's attempt key with its payment's position: the same one records the tip once. */
  attempt_key: string;
}

export type TipStatus = 'active' | 'voided';
export type MethodType = 'cash' | 'card' | 'transfer' | 'other';

/** `TipOut`: a tip as the list and the windows read it. */
export interface TipOut {
  id: string;
  /** `null`: to the pool. */
  sale_id: string | null;
  sale_number: string;
  pool: boolean;
  /** `null`: unassigned. */
  member_id: string | null;
  member_name: string;
  method_id: string;
  method_name: string;
  method_type: MethodType;
  amount: number;
  status: TipStatus;
  created_at: string;
  created_by: string;
  adjusted_at: string | null;
  adjusted_by: string;
  adjust_reason: string;
  voided_at: string | null;
  voided_by: string;
  void_reason: string;
}

/** `TipAddIn` from the Tips screen: of a sale by its number with its payment method, or cash to the pool. */
export type TipRecordIn = { sale: string; method_id: string; amount: number } | { pool: true; amount: number };

export interface TipListIn {
  limit: number;
  offset: number;
  search?: string;
  member_id?: string;
  method_type?: MethodType;
  status?: TipStatus;
  /** Business days, ISO, both included. */
  date_from?: string;
  date_to?: string;
}

export interface TipPage {
  rows: TipOut[];
  total: number;
  limit: number;
  offset: number;
}

/** `TipPatchIn`: only what changes, with why. */
export interface TipPatchIn {
  id: string;
  amount?: number;
  member_id?: string;
  reason: string;
}

export interface TipVoidIn {
  id: string;
  reason: string;
}

/** `Suggestion`: a percentage of the check's total before discounts, or an amount in cents; one of the two. */
export type Suggestion = { percent: number; amount?: null } | { amount: number; percent?: null };

export interface MethodSuggestionsOut {
  method_id: string;
  method_name: string;
  method_type: MethodType;
  suggestions: Suggestion[];
}

export interface SettingsOut {
  enabled: boolean;
  allow_custom: boolean;
  /** Which suggestion comes chosen, 1 to 3; 0: «No tip». */
  preselected: number;
  methods: MethodSuggestionsOut[];
}

/** `SettingsPatchIn`: only what is sent changes. */
export interface SettingsPatchIn {
  enabled?: boolean;
  allow_custom?: boolean;
  preselected?: number;
  methods?: { method_id: string; suggestions: Suggestion[] }[];
}

/** `FiguresOut`: some tips by payment method, in cents, and how many. */
export interface TipFiguresOut {
  card: number;
  cash: number;
  /** Any other way: transfer, Bizum… */
  other: number;
  total: number;
  count: number;
}

export type ReportBy = 'person' | 'shift';

export interface ReportIn {
  by: ReportBy;
  /** Business days, ISO; without them, today. */
  date_from?: string;
  date_to?: string;
}

/** `ReportRowOut`: a person's tips or, by shift, a clocked working day's; nobody's: unassigned, or outside every day. */
export interface ReportRowOut extends TipFiguresOut {
  member_id: string | null;
  member_name: string;
  shift_id: string | null;
  clock_in_at: string | null;
  /** `null` while the working day is still open. */
  clock_out_at: string | null;
}

export interface ReportOut {
  by: ReportBy;
  date_from: string;
  date_to: string;
  /** By shift, `false` when Time clock is off: no rows. */
  shifts_available: boolean;
  rows: ReportRowOut[];
  totals: TipFiguresOut;
}

/** `MineOut`: the caller's own tips of today and of the week, from Monday. */
export interface MineOut {
  member_name: string;
  today: string;
  week_from: string;
  day: TipFiguresOut;
  week: TipFiguresOut;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'tip.suggestion.get': { input: SuggestionIn; output: SuggestionOut };
    'tip.tip.add': { input: TipAddIn | TipRecordIn; output: TipOut };
    'tip.tip.list': { input: TipListIn; output: TipPage };
    'tip.tip.update': { input: TipPatchIn; output: TipOut };
    'tip.tip.void': { input: TipVoidIn; output: TipOut };
    'tip.settings.get': { input: Record<string, never>; output: SettingsOut };
    'tip.settings.update': { input: SettingsPatchIn; output: SettingsOut };
    'tip.report.get': { input: ReportIn; output: ReportOut };
    'tip.report.mine': { input: Record<string, never>; output: MineOut };
  }
}
