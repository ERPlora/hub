// Types of the verifactu app's operations for the SDK (`useLive`, `useCommand`), from apps/verifactu/schemas.py.
// Written by hand, as the other apps' are, until V3 generates them from `/api/openapi.json`. Keep it in step with
// schemas.py and with `frontend/generated/operations.json`. One input per operation (ninja's parity): no path
// parameters, a record's id or its invoice's number travels in the input. Money is whole cents with a sign;
// dates are ISO `YYYY-MM-DD`; moments ISO 8601.
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type RecordStatus = 'pending' | 'sent' | 'accepted' | 'accepted_with_errors' | 'rejected';
export type RecordType = 'alta' | 'anulacion';
export type Environment = 'testing' | 'production';
export type Route = 'erplora' | 'own';
export type CertificateKind = 'seal' | 'representative' | 'personal' | 'unknown';
export type InvoiceType = 'F1' | 'F2' | 'F3' | 'R1' | 'R2' | 'R3' | 'R4' | 'R5';
export type EventKind =
  | 'record_created'
  | 'deferred'
  | 'accepted'
  | 'accepted_with_errors'
  | 'failed'
  | 'queue_processed'
  | 'queue_retried'
  | 'chain_valid'
  | 'chain_broken'
  | 'aeat_queried'
  | 'chain_recovered'
  | 'connection_test'
  | 'config_changed';
export type Severity = 'debug' | 'info' | 'warning' | 'error' | 'critical';
export type Representation = 'none' | 'submitted' | 'approved' | 'returned' | 'revoked';

/** The documents of a signed authorisation (VERIFACTU-F05). */
export type RepresentationDocument = 'signed_model' | 'id_copy' | 'signature_sample' | 'representation_proof';

/** The signed authorisation: as the account says it, what this Hub sent and the steps it was told. */
export interface RepresentationOut {
  status: Representation;
  updated_at: string | null;
  reason: string;
  /** ERPlora's account has linked this business: the authorisation can be sent from here. */
  linked: boolean;
  /** Invoicing's issuer is a company: who signs for it and the proof of representation are asked. */
  company: boolean;
  submission: {
    version: number;
    submitted_at: string | null;
    document_type: 'dni' | 'nie';
    documents: RepresentationDocument[];
  } | null;
  /** Newest first. */
  history: { status: Representation; at: string; version: number | null; reason: string }[];
}

/** The signed authorisation and its documents, each a PDF in base64 (5 MB at most). */
export interface RepresentationSubmitIn {
  signer_tax_id?: string;
  signer_name?: string;
  signer_document_type: 'dni' | 'nie';
  signed_model_base64: string;
  id_copy_base64: string;
  signature_sample_base64?: string;
  representation_proof_base64?: string;
}

/** The official model (Anexo I of Convenio 17) with Invoicing's issuer written in, a PDF in base64. */
export interface RepresentationModelOut {
  filename: string;
  content_type: string;
  content_base64: string;
}

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A record by its id or by its invoice's number. */
export interface RecordRefIn {
  record_id?: string;
  invoice_number?: string;
}

export type NoInput = Record<string, never>;

export interface WaitOut {
  code: string;
  message: string;
}

export interface RecordRowOut {
  id: string;
  sequence: number;
  record_type: RecordType;
  invoice_id: string;
  invoice_number: string;
  issue_date: string;
  invoice_type: string;
  issuer_name: string;
  issuer_nif: string;
  total_amount: number | null;
  environment: Environment;
  status: RecordStatus;
  correction: boolean;
  qr_url: string;
  created_at: string;
}

export interface EventOut {
  id: string;
  created_at: string;
  kind: EventKind;
  severity: Severity;
  message: string;
  record_id: string | null;
  invoice_number: string;
}

export interface InvoiceRefOut {
  issuer_nif: string;
  number: string;
  issue_date: string;
}

export interface RecordOut extends RecordRowOut {
  operation_date: string | null;
  rectification_kind: string;
  rectified: InvoiceRefOut[];
  substituted: InvoiceRefOut[];
  description: string;
  recipient_name: string;
  recipient_tax_id: string;
  recipient_country: string;
  base_amount: number | null;
  tax_amount: number | null;
  previous_rejection: string;
  corrects_id: string | null;
  cancels_id: string | null;
  previous_fingerprint: string;
  previous_number: string;
  generated_at: string;
  fingerprint: string;
  qr_svg: string;
  envelope: string;
  attempts: number;
  next_attempt_at: string | null;
  transmitted_at: string | null;
  transmission_id: string | null;
  envelope_digest: string;
  incident: boolean;
  csv: string;
  aeat_code: string;
  aeat_message: string;
  waiting: WaitOut[];
  can_transmit: boolean;
  can_correct: boolean;
  can_cancel: boolean;
  events: EventOut[];
}

export interface RecordSummaryOut {
  id: string;
  invoice_id: string;
  invoice_number: string;
  record_type: RecordType;
  invoice_type: string;
  sequence: number;
  environment: Environment;
  status: RecordStatus;
  fingerprint: string;
  qr_url: string;
  qr_svg: string;
  csv: string;
}

export interface RecordCreateOut {
  record: RecordSummaryOut;
  already: boolean;
}

export interface QueueRowOut {
  id: string;
  invoice_number: string;
  record_type: RecordType;
  environment: Environment;
  attempts: number;
  status: RecordStatus;
  next_attempt_at: string | null;
  last_error: string;
  created_at: string;
}

export interface ReconcileOut {
  held: boolean;
  record: RecordSummaryOut;
}

export interface TransmitOut {
  chains: number;
  sent: number;
  accepted: number;
  accepted_with_errors: number;
  rejected: number;
  waiting: number;
  reason: string;
  message: string;
}

export interface AeatRecordOut {
  id: string;
  issuer_nif: string;
  environment: Environment;
  invoice_number: string;
  issue_date: string | null;
  fingerprint: string;
  state: string;
  csv: string;
  generated_on: string | null;
  queried_at: string;
}

export interface ChainOut {
  issuer_nif: string;
  environment: Environment;
  sequence: number;
  last_number: string;
  last_issue_date: string | null;
  last_fingerprint: string;
  anchored_at: string | null;
  anchor_source: string;
  validated_at: string | null;
  valid: boolean | null;
  total: number;
  first_invalid_sequence: number | null;
}

export interface ChainStatusOut {
  issuer_nif: string;
  environment: Environment;
  chains: ChainOut[];
}

export interface DiagnosticOut {
  ran_at: string;
  environment: Environment;
  route: Route;
  issuer_ready: boolean;
  route_ready: boolean;
  gateway_configured: boolean;
  gateway_ready: boolean | null;
  gateway_detail: string;
  can_send: boolean;
  reasons: WaitOut[];
}

export interface ConfigOut {
  environment: Environment;
  route: Route;
  production_since: string | null;
  production_open: boolean;
  can_go_back: boolean;
  gateway_configured: boolean;
  issuer_nif: string;
  issuer_name: string;
  producer: {
    name: string;
    nif: string;
    system_name: string;
    system_id: string;
    version: string;
    installation: string;
    only_verifactu: string;
    multi_ot: string;
    /** IndicadorMultiplesOT: always «S» (ERPlora serves several taxpayers). */
    multiple_ot: string;
  };
  declaration_version: string;
  declaration_url: string;
  account_url: string;
  own_certificate: {
    loaded: boolean;
    holder: string;
    holder_tax_id: string;
    kind: CertificateKind | '';
    uploaded_at: string | null;
    expires_at: string | null;
    expires_in_days: number | null;
  };
  representation: RepresentationOut;
  synced_at: string | null;
  route_ready: boolean;
  reasons: WaitOut[];
  /** Why new sales and invoices are refused now (production without a way to the AEAT); null when they are not. */
  issue_blocker: WaitOut | null;
  live_blockers: WaitOut[];
}

export interface ChainValidationOut {
  issuer_nif: string;
  environment: Environment;
  valid: boolean;
  total: number;
  first_invalid_sequence: number | null;
}

export interface RecoveryOut {
  issuer_nif: string;
  environment: Environment;
  sequence: number;
  invoice_number: string;
  fingerprint: string;
  found: number;
}

export interface RecordListIn extends PageIn {
  search?: string;
  status?: RecordStatus;
  record_type?: RecordType;
  invoice_type?: InvoiceType;
  environment?: Environment;
  issue_date_from?: string;
  issue_date_to?: string;
  total_amount_from?: number;
  total_amount_to?: number;
  sort?: 'created_at' | 'sequence' | 'invoice_number' | 'issue_date' | 'invoice_type' | 'issuer_name' | 'total_amount' | 'environment' | 'status';
  dir?: SortDir;
}

export interface ContingencyListIn extends PageIn {
  search?: string;
  environment?: Environment;
  sort?: 'next_attempt_at' | 'invoice_number' | 'attempts' | 'status' | 'created_at';
  dir?: SortDir;
}

/** How the AEAT's query names the state of a record it holds (`EstadoRegistro`). */
export type AeatState = 'Correcto' | 'AceptadoConErrores' | 'Anulado';

export interface AeatRecordListIn extends PageIn {
  search?: string;
  state?: AeatState;
  issue_date_from?: string;
  issue_date_to?: string;
  sort?: 'generated_on' | 'invoice_number' | 'issue_date' | 'fingerprint' | 'state' | 'csv' | 'queried_at';
  dir?: SortDir;
}

export interface EventListIn extends PageIn {
  search?: string;
  kind?: EventKind;
  severity?: Severity;
  date_from?: string;
  date_to?: string;
  sort?: 'created_at' | 'kind' | 'severity';
  dir?: SortDir;
}

export interface IssuerIn {
  issuer_nif?: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'verifactu.config.get': { input: NoInput; output: ConfigOut };
    'verifactu.config.update': { input: { route: Route }; output: ConfigOut };
    'verifactu.config.go_live': { input: NoInput; output: ConfigOut };
    'verifactu.config.back_to_testing': { input: NoInput; output: ConfigOut };
    'verifactu.certificate.upload': { input: { p12_base64: string; password: string }; output: ConfigOut };
    'verifactu.representation.submit': { input: RepresentationSubmitIn; output: ConfigOut };
    'verifactu.representation.model': { input: NoInput; output: RepresentationModelOut };
    'verifactu.certificate.remove': { input: NoInput; output: ConfigOut };
    'verifactu.record.list': { input: RecordListIn; output: Page<RecordRowOut> };
    'verifactu.record.get': { input: RecordRefIn; output: RecordOut };
    'verifactu.record.by_invoice': { input: { invoice_id: string }; output: { record: RecordSummaryOut | null } };
    'verifactu.record.create': { input: { invoice_id?: string; number?: string }; output: RecordCreateOut };
    'verifactu.record.correct': { input: RecordRefIn; output: RecordCreateOut };
    'verifactu.record.cancel': { input: RecordRefIn & { reason: string }; output: RecordCreateOut };
    'verifactu.record.transmit': { input: RecordRefIn; output: TransmitOut };
    'verifactu.record.reconcile': { input: RecordRefIn; output: ReconcileOut };
    'verifactu.contingency.list': { input: ContingencyListIn; output: Page<QueueRowOut> };
    'verifactu.contingency.process': { input: NoInput; output: TransmitOut };
    'verifactu.contingency.retry': { input: RecordRefIn; output: RecordSummaryOut };
    'verifactu.event.list': { input: EventListIn; output: Page<EventOut> };
    'verifactu.stats.compliance_summary': {
      input: NoInput;
      output: { unsent_count: number; pending_count: number; rejected_count: number; accepted_count: number; total: number; environment: Environment };
    };
    'verifactu.stats.records_by_status': { input: NoInput; output: { rows: { status: RecordStatus; label: string; total: number }[] } };
    'verifactu.stats.contingency_summary': { input: NoInput; output: { queued_count: number; overdue_count: number; severity: 'ok' | 'warning' | 'danger' } };
    'verifactu.stats.events_recent': { input: { limit?: number }; output: { rows: EventOut[] } };
    'verifactu.aeat_record.list': { input: AeatRecordListIn; output: Page<AeatRecordOut> };
    'verifactu.aeat.query': { input: IssuerIn & { year?: number; month?: number }; output: { count: number; rows: AeatRecordOut[] } };
    'verifactu.chain.status': { input: IssuerIn; output: ChainStatusOut };
    'verifactu.chain.validate': { input: IssuerIn; output: ChainValidationOut };
    'verifactu.chain.recover_from_aeat': { input: IssuerIn; output: RecoveryOut };
    'verifactu.chain.recover_manual': { input: IssuerIn & { fingerprint: string; invoice_number: string; issue_date: string }; output: RecoveryOut };
    'verifactu.diagnostic.last': { input: NoInput; output: { result: DiagnosticOut | null } };
    'verifactu.diagnostic.run': { input: NoInput; output: DiagnosticOut };
    'verifactu.test_invoice.create': { input: NoInput; output: { invoice_id: string; number: string; record: RecordSummaryOut } };
  }
}
