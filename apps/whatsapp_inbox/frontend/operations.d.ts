// Types of the WhatsApp inbox's operations for the SDK (`useLive`, `useCommand`), from
// apps/whatsapp_inbox/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and with `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, a conversation's `id` travels in the input.
// Instants are ISO 8601 strings; person ids are numbers (the platform's user ids).
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type ConversationStatus = 'open' | 'pending' | 'closed';
export type MessageStatus = 'received' | 'queued' | 'sending' | 'sent' | 'delivered' | 'read' | 'failed';
export type TemplateCategory = 'UTILITY' | 'MARKETING' | 'AUTHENTICATION';
export type TemplateStatus = 'APPROVED' | 'PENDING' | 'REJECTED' | 'PAUSED' | 'DISABLED' | 'DELETED';
export type ChannelStatus = 'not_connected' | 'connected' | 'reconnect_needed';
export type SendBlocked = 'not_connected' | 'cap_reached' | 'unconfigured';

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A conversation by its id, or by its number or the customer's name. */
export interface ConversationRefIn {
  id?: string;
  conversation?: string;
}

// ── Conversations ──────────────────────────────────────────────────────────────────────────────

export interface ConversationListIn extends PageIn {
  search?: string;
  status?: ConversationStatus;
  /** `me`, `none` or a person's id. */
  assigned?: string;
  unread?: boolean;
  customer_id?: string;
  sort?: 'last_message_at' | 'contact' | 'phone' | 'status' | 'unread_count' | 'assigned_to';
  dir?: SortDir;
}

export interface ConversationOut {
  id: string;
  phone: string;
  contact_name: string;
  display_name: string;
  customer_id: string | null;
  customer_name: string;
  assigned_to_id: number | null;
  assigned_to_name: string;
  status: ConversationStatus;
  unread_count: number;
  last_message_at: string | null;
  last_message_preview: string;
  last_message_direction: '' | 'inbound' | 'outbound';
  /** Meta's type of the last message: the inbox names it when there is no text. */
  last_message_kind: string;
  last_inbound_at: string | null;
  created_at: string;
}

export interface ConversationDetailOut extends ConversationOut {
  window_open: boolean;
  window_expires_at: string | null;
  can_send: boolean;
  send_blocked: SendBlocked | null;
}

export interface ByPhoneIn {
  phone: string;
}

export interface ByPhoneOut {
  phone_is_international: boolean;
  phone: string;
  conversation_id: string | null;
}

export type SummaryIn = Record<string, never>;

export interface SummaryOut {
  open: number;
  unread_conversations: number;
  awaiting_reply: number;
  cap_reached: boolean;
}

export interface AssignIn extends ConversationRefIn {
  assignee_id?: number;
  /** A name, username or email, or `me`. */
  assignee?: string;
  unassign?: boolean;
  only_if_unassigned?: boolean;
}

export interface SetStatusIn extends ConversationRefIn {
  status: ConversationStatus;
}

export interface LinkCustomerIn extends ConversationRefIn {
  customer_id?: string;
  customer?: string;
  create?: boolean;
  unlink?: boolean;
}

export interface ErasedOut {
  id: string;
}

// ── Messages ───────────────────────────────────────────────────────────────────────────────────

export interface MessageListIn extends ConversationRefIn, PageIn {}

export interface MessageOut {
  id: string;
  conversation_id: string;
  direction: 'inbound' | 'outbound';
  origin: 'customer' | 'phone_app' | 'hub';
  source: 'live' | 'history';
  kind: string;
  body: string;
  media_url: string;
  media_mime_type: string;
  media_filename: string;
  media_caption: string;
  template_name: string;
  status: MessageStatus;
  error_code: string;
  error_message: string;
  /** Meta's id; `null` while the message has not left. */
  wa_message_id: string | null;
  reply_to: string;
  sent_by_name: string;
  sent_at: string;
  status_at: string | null;
}

export interface TemplateSendIn {
  name: string;
  language?: string;
  variables?: string[];
}

export interface SendIn {
  id?: string;
  to?: string;
  conversation?: string;
  template?: TemplateSendIn;
  text?: string;
  /** A key of the caller's own per message, the same on a retry: never sent twice. */
  client_message_id: string;
}

export interface MessageRefIn {
  id: string;
}

// ── Notes ──────────────────────────────────────────────────────────────────────────────────────

export interface NoteListIn extends ConversationRefIn, PageIn {}

export interface NoteAddIn extends ConversationRefIn {
  text: string;
}

export interface NoteRefIn {
  id: string;
}

export interface NoteOut {
  id: string;
  conversation_id: string;
  text: string;
  author_id: number | null;
  author_name: string;
  created_at: string;
  can_delete: boolean;
}

// ── Templates, channel, team ───────────────────────────────────────────────────────────────────

export interface TemplateListIn extends PageIn {
  search?: string;
  status?: TemplateStatus;
  category?: TemplateCategory;
  language?: string;
}

export interface TemplateOut {
  id: string;
  name: string;
  language: string;
  category: TemplateCategory;
  status: TemplateStatus;
  header: string;
  body: string;
  footer: string;
  variables: number;
  rejected_reason: string;
  synced_at: string | null;
}

export type ChannelGetIn = Record<string, never>;

export interface ChannelOut {
  status: ChannelStatus;
  phone_number: string;
  display_name: string;
  monthly_limit: number;
  monthly_usage: number;
  cap_reached: boolean;
  synced_at: string | null;
  manage_url: string;
}

export interface AgentListIn extends PageIn {
  search?: string;
}

export interface AgentOut {
  id: number;
  name: string;
  role: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'whatsapp_inbox.conversation.list': { input: ConversationListIn; output: Page<ConversationOut> };
    'whatsapp_inbox.conversation.detail': { input: ConversationRefIn; output: ConversationDetailOut };
    'whatsapp_inbox.conversation.by_phone': { input: ByPhoneIn; output: ByPhoneOut };
    'whatsapp_inbox.conversation.summary': { input: SummaryIn; output: SummaryOut };
    'whatsapp_inbox.conversation.mark_read': { input: ConversationRefIn; output: ConversationOut };
    'whatsapp_inbox.conversation.assign': { input: AssignIn; output: ConversationOut };
    'whatsapp_inbox.conversation.set_status': { input: SetStatusIn; output: ConversationOut };
    'whatsapp_inbox.conversation.link_customer': { input: LinkCustomerIn; output: ConversationOut };
    'whatsapp_inbox.conversation.erase': { input: ConversationRefIn; output: ErasedOut };
    'whatsapp_inbox.message.list': { input: MessageListIn; output: Page<MessageOut> };
    'whatsapp_inbox.message.send': { input: SendIn; output: MessageOut };
    'whatsapp_inbox.message.retry': { input: MessageRefIn; output: MessageOut };
    'whatsapp_inbox.note.list': { input: NoteListIn; output: Page<NoteOut> };
    'whatsapp_inbox.note.add': { input: NoteAddIn; output: NoteOut };
    'whatsapp_inbox.note.delete': { input: NoteRefIn; output: ErasedOut };
    'whatsapp_inbox.template.list': { input: TemplateListIn; output: Page<TemplateOut> };
    'whatsapp_inbox.channel.get': { input: ChannelGetIn; output: ChannelOut };
    'whatsapp_inbox.agent.list': { input: AgentListIn; output: Page<AgentOut> };
  }
}
