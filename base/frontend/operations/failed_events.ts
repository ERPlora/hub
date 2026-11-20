// Types of base/schemas/failed_events.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.FailedEventOut`: a delivery the relay gave up on. */
export interface FailedEvent {
  /** The delivery: what is resent or discarded. */
  id: string;
  event_id: string;
  name: string;
  source_app: string;
  source_app_name: string;
  target_app: string;
  target_app_name: string;
  attempts: number;
  occurred_at: string;
  last_error: string;
  /** False: the app it was for is no longer on in this business. */
  retryable: boolean;
}

/** `base.FailedEventListOut`. */
export interface FailedEventPage {
  items: FailedEvent[];
  total: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.failed_event.list': { input: { limit?: number; offset?: number }; output: FailedEventPage };
    'base.failed_event.retry': { input: { id: string }; output: { id: string } };
    'base.failed_event.retry_all': { input: NoInput; output: { count: number } };
    'base.failed_event.discard': { input: { id: string; reason?: string }; output: { id: string } };
  }
}
