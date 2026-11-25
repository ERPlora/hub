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

/** `TipOut`, what the charge sheet reads of it. */
export interface TipOut {
  id: string;
  sale_id: string | null;
  amount: number;
  status: 'active' | 'voided';
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'tip.suggestion.get': { input: SuggestionIn; output: SuggestionOut };
    'tip.tip.add': { input: TipAddIn; output: TipOut };
  }
}
