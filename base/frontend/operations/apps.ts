// Types of base/schemas/apps.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** Where a module's right comes from (`base.entitlement`): free, the plan, a purchase, with an app that needs it,
 *  or none (it needs a subscription, bought on erplora.com). */
export type AppRight = 'free' | 'plan' | 'purchase' | 'required' | 'missing';

/** `base.AppOut`: a module of the deployment as the Apps screen paints it. */
export interface AppRow {
  id: string;
  name: string;
  icon: string;
  category: string;
  category_label: string;
  summary: string;
  /** Bought on erplora.com; the Store has its price. */
  premium: boolean;
  right: AppRight;
  /** «off»: the business turned it off (or never on); «blocked»: no right to it; «creating»: its tables are being made
   *  in the business's own database; «failed»: making them failed (tried again later, or `base.app.retry`). */
  state: 'on' | 'off' | 'blocked' | 'creating' | 'failed';
  /** Turned on by the business itself (what the plan's limit counts); what came along with another app is not. */
  chosen: boolean;
  /** The first screen of its menu this person may open; null: no «Open». */
  path: string | null;
  /** What it needs, transitively (it comes along with it), and the apps on that need it (they go off first): ids. */
  requires: string[];
  required_by: string[];
  /** Why turning it on (when off) or off (when on) is refused, in the reader's language: neither is offered. */
  refusal: string | null;
  /** The business's country requires it on (hub#997): «Mandatory in {country}»; once on, it never goes off there. */
  mandatory: boolean;
}

/** `base.AppListOut`. */
export interface AppList {
  apps: AppRow[];
  /** The business's country by its name in the reader's language (without one, Spain): what «Mandatory in …» says. */
  country_name: string;
  /** erplora.com's Store of this business's modules. */
  store_url: string;
  /** erplora.com's plans of this business, where a higher limit of apps is bought. */
  plan_url: string;
  /** How many apps the plan lets the business choose; null: no limit. */
  max_apps: number | null;
  /** How many it chose and are on (what came along with them does not count). */
  enabled: number;
}

/** `base.AppChangeIn`: one app of the business, by its name as the person says it or by its id. */
export interface AppChangeIn {
  app: string;
}

/** `base.AppChangeOut`: the app as it is now, and the apps that went on (or off) with it; «creating» (202): its tables
 *  are being made, and `base.app.list` says when it is on. */
export interface AppChange {
  app: string;
  state: 'on' | 'off' | 'creating';
  chosen: boolean;
  along: { id: string; name: string }[];
  /** It was on already (turning it on) or off already (turning it off): nothing went on or off. */
  already: boolean;
}

/** `base.AppRefIn`: one app of the business, by its name or its id. */
export interface AppRefIn {
  app: string;
}

/** `base.AppRefOut`: which app a name names, with its state as the Apps screen says it. */
export interface AppRef {
  id: string;
  name: string;
  state: 'on' | 'off' | 'blocked' | 'creating' | 'failed';
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.app.list': { input: NoInput; output: AppList };
    'base.app.enable': { input: AppChangeIn; output: AppChange };
    'base.app.disable': { input: AppChangeIn; output: AppChange };
    'base.app.get': { input: AppRefIn; output: AppRef };
    'base.app.retry': { input: AppChangeIn; output: AppChange };
  }
}
