// Types of the printing app's operations for the SDK (`useLive`, `useCommand`), from apps/printing/schemas.py.
// Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and with `frontend/generated/operations.json`. One
// input per operation (ninja's parity): no path parameters. Dates are ISO 8601 strings.
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type Usage = 'receipt' | 'kitchen' | 'bar' | 'label';
export type PrinterKind = 'network' | 'usb' | 'bluetooth' | 'system';
export type PaperWidth = 80 | 58;
export type PrinterState = 'ready' | 'waiting' | 'failing' | 'inactive';
export type JobKind = 'document' | 'test_page' | 'drawer';
export type JobFormat = 'receipt' | 'a4';
export type JobStatus = 'pending' | 'sent' | 'done' | 'failed' | 'cancelled';
export type DocumentType =
  | 'receipt'
  | 'kitchen_order'
  | 'invoice'
  | 'delivery_note'
  | 'barcode_label'
  | 'cash_session_report'
  | 'prebill'
  | 'generic';

interface PageIn {
  limit?: number;
  offset?: number;
}

type EmptyIn = Record<string, never>;

// ── Settings ─────────────────────────────────────────────────────────────────────────────────

export interface SettingsOut {
  print_receipt_on_sale: boolean;
  open_drawer_on_sale: boolean;
  receipt_copies: number;
  receipt_printer_id: string | null;
  kitchen_printer_id: string | null;
  bar_printer_id: string | null;
  label_printer_id: string | null;
  updated_at: string | null;
}

/** What changes; a printer by its id or name, `null` = the first active one of its function. */
export interface SettingsPatchIn {
  print_receipt_on_sale?: boolean;
  open_drawer_on_sale?: boolean;
  receipt_copies?: number;
  receipt_printer?: string | null;
  kitchen_printer?: string | null;
  bar_printer?: string | null;
  label_printer?: string | null;
}

// ── Printers ─────────────────────────────────────────────────────────────────────────────────

export interface PrinterIn {
  name: string;
  kind: PrinterKind;
  address?: string;
  port?: number | null;
  paper_width?: PaperWidth;
  usage: Usage;
  is_active?: boolean;
}

export interface PrinterRefIn {
  printer_id?: string;
  printer?: string;
}

export interface PrinterUpdateIn extends PrinterRefIn {
  name?: string;
  kind?: PrinterKind;
  address?: string;
  port?: number | null;
  paper_width?: PaperWidth;
  usage?: Usage;
  is_active?: boolean;
}

export interface PrinterListIn extends PageIn {
  search?: string;
  usage?: Usage;
  kind?: PrinterKind;
  is_active?: boolean;
  sort?: 'name' | 'usage' | 'kind' | 'created_at';
  dir?: SortDir;
}

export interface PrinterOut {
  id: string;
  name: string;
  kind: PrinterKind;
  address: string;
  port: number | null;
  paper_width: number;
  usage: Usage;
  is_active: boolean;
  /** The printer id the app's print commands take: `network:<ip>:<port>`, `bluetooth:<mac>`, `usb:<queue>`, `system`. */
  target: string;
  oldest_pending_at: string | null;
  state: PrinterState;
  pending: number;
  last_printed_at: string | null;
  last_failed_at: string | null;
  last_error: string;
  created_at: string;
}

export interface PrinterStatusOut {
  printer: PrinterOut;
  is_default: boolean;
  pending: number;
  oldest_pending_at: string | null;
  sent: number;
  failed: number;
}

// ── Jobs ─────────────────────────────────────────────────────────────────────────────────────

export interface JobCreateIn {
  job_key?: string;
  document_type: DocumentType;
  document?: Record<string, unknown>;
  format?: JobFormat;
  html?: string;
  usage?: Usage;
  printer?: string;
  copies?: number;
  automatic?: boolean;
  /** With `automatic`: false keeps the drawer shut whatever the settings (a checkout with no cash). */
  open_drawer?: boolean;
  /** ISO 4217, for the amounts' decimals; the business's without it. */
  currency?: string;
  source_app?: string;
  source_ref?: string;
}

export interface JobOut {
  id: string;
  job_key: string;
  kind: JobKind;
  document_type: string;
  reference: string;
  format: JobFormat;
  usage: Usage;
  printer_id: string | null;
  printer_name: string | null;
  copies: number;
  open_drawer: boolean;
  status: JobStatus;
  attempts: number;
  /** Sent: the device must answer before this moment. */
  leased_until: string | null;
  stale: boolean;
  retryable: boolean;
  cancellable: boolean;
  device: string;
  last_error: string;
  source_app: string;
  created_at: string;
  created_by: string;
  sent_at: string | null;
  printed_at: string | null;
  failed_at: string | null;
  retried_at: string | null;
  retried_by: string;
  cancelled_at: string | null;
  cancelled_by: string;
  cancel_reason: string;
}

export interface JobCreateOut {
  job: JobOut | null;
  duplicate: boolean;
  skipped: 'print_on_sale_off' | null;
}

export interface JobListIn extends PageIn {
  search?: string;
  status?: JobStatus;
  usage?: Usage;
  printer_id?: string;
  sort?: 'created_at' | 'status' | 'usage' | 'attempts';
  dir?: SortDir;
}

export interface JobRefIn {
  job_id?: string;
  reference?: string;
}

export interface JobCancelIn extends JobRefIn {
  reason?: string;
}

export interface UsageSummary {
  usage: Usage;
  printers: number;
  default_printer: string | null;
  /** The printer its next job goes to now (the chosen one if active, else the first active one). */
  prints_on: string | null;
  pending: number;
  oldest_pending_at: string | null;
  sent: number;
  failed: number;
}

export interface JobSummaryOut {
  usages: UsageSummary[];
  pending: number;
  sent: number;
  failed: number;
}

// ── The device that prints (base's /ws/print) ────────────────────────────────────────────────

export interface JobClaimIn {
  printers: string[];
  device: string;
}

export interface HostJobOut {
  id: string;
  kind: JobKind;
  printer_id: string;
  target: string;
  paper_width: number;
  document_type: string;
  document: Record<string, unknown>;
  /** What the copies after the first print: a receipt or an invoice marked `duplicate`; none with one copy. */
  copy_document: Record<string, unknown> | null;
  format: JobFormat;
  html: string;
  copies: number;
  open_drawer: boolean;
  attempts: number;
  /** When the device's time to answer runs out (90 s after it took the job). */
  leased_until: string;
}

export interface JobAckOut {
  confirmed: boolean;
  job: JobOut;
}

// ── The devices that print (PRINTING-F18) ────────────────────────────────────────────────────

export interface DevicePrinterOut {
  id: string;
  name: string;
  usage: Usage;
  is_active: boolean;
}

/** Who prints a function: the Home's «Set up your printer» (`covered`, receipts) and the bell's «Nothing is printing». */
export interface CoverageOut {
  usage: Usage;
  /** A device set up here reaches an active printer of the function on receipt paper. */
  covered: boolean;
  /** Its jobs waiting that no device set up here can print. */
  count: number;
}

/** A device set up to print. Its own id (X-Device-Id) is never sent back: it proves the device. */
export interface DeviceOut {
  /** The registration's id: what «Edit» and «Retire» name. */
  id: string;
  name: string;
  printers: DevicePrinterOut[];
  registered_at: string;
  registered_by: string;
  /** When it last asked for a job; null = never yet. */
  last_seen_at: string | null;
  /** It is the device the page runs on. */
  this_device: boolean;
}

export interface DeviceRegisterIn {
  name: string;
  printers: string[];
}

export interface DeviceRefIn {
  device_id: string;
}

export interface DeviceUpdateIn extends DeviceRefIn {
  name?: string;
  printers?: string[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'printing.settings.get': { input: EmptyIn; output: SettingsOut };
    'printing.settings.update': { input: SettingsPatchIn; output: SettingsOut };
    'printing.printer.list': { input: PrinterListIn; output: Page<PrinterOut> };
    'printing.printer.get': { input: PrinterRefIn; output: PrinterOut };
    'printing.printer.status': { input: PrinterRefIn; output: PrinterStatusOut };
    'printing.printer.create': { input: PrinterIn; output: PrinterOut };
    'printing.printer.update': { input: PrinterUpdateIn; output: PrinterOut };
    'printing.printer.test': { input: PrinterRefIn; output: JobOut };
    'printing.job.list': { input: JobListIn; output: Page<JobOut> };
    'printing.job.summary': { input: EmptyIn; output: JobSummaryOut };
    'printing.job.create': { input: JobCreateIn; output: JobCreateOut };
    'printing.job.claim': { input: JobClaimIn; output: { job: HostJobOut | null } };
    'printing.job.complete': { input: { job_id: string; device: string; attempt: number }; output: JobAckOut };
    'printing.job.fail': { input: { job_id: string; device: string; attempt: number; error: string }; output: JobAckOut };
    'printing.job.retry': { input: JobRefIn; output: JobOut };
    'printing.job.cancel': { input: JobCancelIn; output: JobOut };
    'printing.device.list': { input: PageIn; output: Page<DeviceOut> };
    'printing.device.register': { input: DeviceRegisterIn; output: DeviceOut };
    'printing.device.update': { input: DeviceUpdateIn; output: DeviceOut };
    'printing.device.retire': { input: DeviceRefIn; output: DeviceOut };
    'printing.device.coverage': { input: { usage: Usage }; output: CoverageOut };
  }
}
