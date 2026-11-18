// What `verifactu.config.get` answers for a business in testing on ERPlora's route, nothing signed nor uploaded yet:
// the starting point of the Configuration and Settings pages' tests, each overriding what it looks at.
import type { ConfigOut } from '../operations';

export const CONFIG: ConfigOut = {
  environment: 'testing',
  route: 'erplora',
  erplora_route_available: true,
  production_since: null,
  production_open: false,
  can_go_back: true,
  gateway_configured: false,
  issuer_nif: 'B12345674',
  issuer_name: 'Peluquería Ana SL',
  producer: { name: 'ERPLORA CLOUD SL', nif: 'B27593136', system_name: 'ERPlora Hub', system_id: 'EC', version: 'dev', installation: 'a', only_verifactu: 'S', multi_ot: 'S', multiple_ot: 'S' },
  declaration_version: 'v1',
  declaration_url: 'https://erplora.com/legal/declaracion-responsable/v1/',
  account_url: 'https://erplora.com',
  own_certificate: { loaded: false, holder: '', holder_tax_id: '', kind: '', uploaded_at: null, expires_at: null, expires_in_days: null },
  representation: { status: 'none', updated_at: null, reason: '', linked: true, company: true, submission: null, history: [] },
  synced_at: null,
  route_ready: true,
  route_ready_for_production: false,
  reasons: [],
  issue_blocker: null,
  live_blockers: [],
};

export const CONFIG_WITHOUT_ERPLORA_ROUTE: ConfigOut = {
  ...CONFIG,
  erplora_route_available: false,
};

export const LOADED_CERTIFICATE: ConfigOut['own_certificate'] = {
  loaded: true,
  holder: 'ACME SL',
  holder_tax_id: 'B12345674',
  kind: 'representative',
  uploaded_at: '2026-10-01T10:00:00Z',
  expires_at: '2027-10-01T10:00:00Z',
  expires_in_days: 351,
};
