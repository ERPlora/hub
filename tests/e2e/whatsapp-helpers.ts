// Shared steps of the WhatsApp inbox e2e (whatsapp-*.spec.ts). erplora.com's doors (`/internal/whatsapp/*`,
// mounted by `base`) are not here yet, so what erplora.com would push — a customer's message, the channel's
// state and its templates — is pushed the way those doors will: by running the app's own system operation
// (`whatsapp_inbox.message.receive`, `whatsapp_inbox.channel.sync`) as the platform, in the hub `a`, through
// `manage.py shell`. Never Meta, never a row written by hand: the operation commits and notifies, and the
// open pages update live. What a run creates is named `e2e.…` and deleted in the spec's `afterAll`.
import { execFileSync } from 'node:child_process';

import type { Page } from '@playwright/test';

import { HUB_DIR, psql, shot } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';

/** Every WhatsApp id, template and card name of a run starts like this. */
export const PREFIX = 'e2e.';

/** A Spanish mobile number of the 699 00x xxx range, unique enough per run (E.164). */
export const e2ePhone = (): string => `+3469900${String(Math.floor(Math.random() * 1e4)).padStart(4, '0')}`;

/** A channel version above any real one: what the spec pushes always wins, and cleanUp finds it. */
let version = 900_000_000 + Math.floor(Date.now() / 1000) % 1_000_000;

const RUN = `
import json, os
from live.context import Scope, system_context
from live.operations import get
op = get(os.environ["WA_OP"])
out = op(system_context(Scope("host", "a")), op.input.model_validate(json.loads(os.environ["WA_PAYLOAD"])))
print(out.model_dump_json())
`;

/** Runs a system operation of the inbox in the hub `a`, as erplora.com's doors will; its output. */
export function system<T = unknown>(op: string, payload: unknown): T {
  const out = execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', RUN], {
    cwd: HUB_DIR,
    encoding: 'utf8',
    env: { ...process.env, WA_OP: op, WA_PAYLOAD: JSON.stringify(payload) },
  });
  const line = out.trim().split('\n').at(-1) ?? '';
  return JSON.parse(line) as T;
}

/** A WhatsApp id of this run. */
export const waId = (): string => `${PREFIX}wamid.${Date.now()}.${Math.floor(Math.random() * 1e6)}`;

/** A customer's text arriving now from `phone` (E.164), as erplora.com pushes it; `over` changes the
 *  message (an attachment, the echo of the owner's phone, an option tapped…). */
export function receive(
  phone: string,
  text: string,
  contactName: string,
  over: Record<string, unknown> = {},
): { id: string; conversation_id: string } {
  return system('whatsapp_inbox.message.receive', {
    wa_message_id: waId(),
    from: phone.replace('+', ''),
    contact_name: contactName,
    direction: 'inbound',
    source: 'live',
    type: 'text',
    text,
    sent_at: new Date().toISOString(),
    ...over,
  });
}

/** The key the Hub sent its last message to `phone` with (what erplora.com's statuses carry). */
export function lastSentKey(phone: string): string {
  return psql(
    `select m.client_message_id from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone.replace(/'/g, '')}' and m.origin = 'hub' order by m.created_at desc limit 1`,
  );
}

/** A delivery status of Meta for the Hub's message sent with `key`, as erplora.com pushes it. */
export function pushStatus(key: string, status: 'sent' | 'delivered' | 'read', wamid: string): void {
  system('whatsapp_inbox.message.update_status', {
    wa_message_id: wamid,
    client_message_id: key,
    status,
    status_at: new Date().toISOString(),
  });
}

/** The screen of `flow` in the three sizes (APP-WHATSAPP_INBOX-1-<flow>-390|834|1440), once it settles and
 *  nothing scrolls sideways; `ready` waits for what the capture must show. Back to 1280×860 after. */
export async function flowShots(page: Page, flow: string, ready: (page: Page) => Promise<void> = async () => {}): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${flow} ${viewport.label}`);
    await page.screenshot({ path: shot(`APP-WHATSAPP_INBOX-1-${flow}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

export interface ChannelPush {
  status: 'not_connected' | 'connected' | 'reconnect_needed';
  monthly_limit?: number;
  monthly_usage?: number;
  templates?: unknown[] | null;
}

/** erplora.com's state of the number (and, when given, the templates Meta holds). */
export function pushChannel(state: ChannelPush): void {
  version += 1;
  const month = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' }).slice(0, 7);
  system('whatsapp_inbox.channel.sync', {
    version,
    status: state.status,
    phone_number: state.status === 'not_connected' ? '' : '+34910000000',
    display_name: state.status === 'not_connected' ? '' : 'e2e. Peluquería',
    monthly_limit: state.monthly_limit ?? 150,
    monthly_usage: state.monthly_usage ?? 12,
    usage_month: month,
    templates: state.templates ?? null,
  });
}

/** A template as erplora.com reports it. */
export const template = (name: string, over: Record<string, unknown> = {}) => ({
  name,
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header: '',
  body: 'Hola {{1}}, te esperamos mañana.',
  footer: '',
  variables: 1,
  rejected_reason: '',
  meta_id: name,
  ...over,
});

/** Deletes what the specs created: their conversations (erased ones too) with their messages and notes,
 *  their templates and the channel row they pushed. Raw SQL has no Django cascade: children first. */
export function cleanUp(): void {
  const byMessage = psql(`select string_agg(distinct conversation_id::text, ',') from whatsapp_inbox_message where wa_message_id like '${PREFIX}%'`);
  const byPhone = psql("select string_agg(id::text, ',') from whatsapp_inbox_conversation where phone like '+3469900%'");
  const ids = [...new Set([...byMessage.split(','), ...byPhone.split(',')].filter(Boolean))];
  if (ids.length) {
    const list = ids.map((id) => `'${id.replace(/'/g, '')}'`).join(',');
    psql(`delete from whatsapp_inbox_note where conversation_id in (${list})`);
    psql(`delete from whatsapp_inbox_message where conversation_id in (${list})`);
    psql(`delete from whatsapp_inbox_conversation where id in (${list})`);
  }
  psql("delete from whatsapp_inbox_template where name like 'e2e_%'");
  psql('delete from whatsapp_inbox_channel where version >= 900000000');
}
