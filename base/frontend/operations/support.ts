// Types of base/schemas/support.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

/** `base.SupportReportIn` («Report a problem» of the user menu, BASE-F108). */
export interface SupportReportInput {
  subject: string;
  description: string;
  /** The hub's screen the person was on. */
  page?: string | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    // «Report a problem» of the user menu (BASE-F108): erplora.com answers the address support writes back to.
    'base.support.report': { input: SupportReportInput; output: { reply_to: string } };
    // The pass to erplora.com (BASE-F11): its address, signed at the click, opens for a minute, once.
    'base.saas_pass.create': { input: { next: 'plan' | 'business' }; output: { url: string } };
  }
}
