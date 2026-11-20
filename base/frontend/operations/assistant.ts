// Types of base/schemas/assistant.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

/** `base.AssistantReportIn`. */
export interface AssistantReportInput {
  message_id: string;
  reason: 'incorrect' | 'harmful' | 'instructions' | 'other';
  comment?: string;
  question?: string;
  answer: string;
  /** Whether its turn brought pages of the web (the turn's `done.web`); left out when the chat does not know. */
  web?: boolean;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    // Assistant; its turn is a stream the shared panel reads itself (@erplora/ui, Assistant/stream.ts).
    'base.assistant.report': { input: AssistantReportInput; output: { sent: boolean; duplicate: boolean } };
    'base.assistant.transcribe': {
      input: { audio: string; mime_type: string; language?: string };
      output: { text: string; language: string };
    };
    // «Read aloud» in a server voice: its route answers the mp3 itself (assistant-hub.ts
    // `speakAloud`); this output is what an integration that accepts only JSON gets.
    'base.assistant.speak': {
      input: { text: string; language?: string; voice?: string };
      output: { content_type: string; content_base64: string };
    };
  }
}
