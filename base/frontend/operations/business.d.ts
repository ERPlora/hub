// Types of base/schemas/business.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.BusinessOut`: the business as erplora.com registered it, each value named in the person's language. */
export interface Business {
  /** On ERPlora's own hub, its issuer's legal name; empty in a demo. */
  name: string;
  /** ISO 3166-1 alpha-2; empty in a demo. */
  country: string;
  country_name: string;
  /** IANA zone: the business's clock. */
  timezone: string;
  language: string;
  language_name: string;
  /** ISO 4217: the country's (the euro without a country). */
  currency: string;
  /** «EUR · Euro». */
  currency_label: string;
  currency_decimals: number;
  demo: boolean;
  /** The business's settings on erplora.com; empty in a demo and on ERPlora's own hub. */
  settings_url: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.business.get': { input: NoInput; output: Business };
  }
}
