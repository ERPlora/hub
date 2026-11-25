// Types of apps/sale/schemas/checkout.py and sales.py for what another app adds to a charge (the tip): the steps of
// the charge sheet and what each payment carries apart from the sale.

/** `CheckoutStepOut`: a step an app on adds to the charge, mounted by its component's name. */
export interface CheckoutStepOut {
  /** «<app>.<step>». */
  key: string;
  app: string;
  /** A component of `apps/<app>/frontend/components/`, without `.vue`. */
  component: string;
}

declare module '../operations' {
  interface PaymentIn {
    /** What another app's step adds to this payment (a tip), in cents: never part of the sale. */
    extra?: number;
    /** Its name on the paper (e.g. «Tip»). */
    extra_label?: string;
  }

  interface SalePaymentOut {
    extra: number;
    /** Empty when nothing was added. */
    extra_label: string;
  }
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'sale.checkout.steps': { input: Record<string, never>; output: { steps: CheckoutStepOut[] } };
  }
}
