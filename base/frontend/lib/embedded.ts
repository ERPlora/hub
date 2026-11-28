// What Django embeds in the page (`base/spa.py`): its JSON blocks, and the shape of `hub-home`.
/** A `<script type="application/json">` block Django embedded (`base/spa.py`); none when missing or broken. */
export function readJsonBlock<T>(id: string, doc: Document = document): T | undefined {
  const text = doc.getElementById(id)?.textContent;
  if (!text) return undefined;
  try {
    return JSON.parse(text) as T;
  } catch {
    return undefined;
  }
}

/** What `base/spa.py` embeds as `hub-home`. */
export interface HubHome {
  name: string;
  plan_url: string;
  /** The person's account on erplora.com (the user menu's «My account»). */
  account_url: string;
  /** «Members» of this business on erplora.com, where people are invited, given a role and removed. */
  members_url?: string;
  /** This business on erplora.com's panel (the bar's «erplora.com», BASE-F11); empty for who may not open it. */
  manage_url?: string;
  /** Whether erplora.com reads the assistant's answers aloud in its voices (`ASSISTANT_SERVER_VOICE`). */
  server_voice?: boolean;
  /** erplora.com's door to the ERPlora app of each system it publishes (hub#683; `lib/app-downloads.ts`). */
  app_downloads?: Record<string, string>;
}
