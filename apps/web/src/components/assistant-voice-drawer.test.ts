// The microphone lives in the drawer (hub#629): voice → text → the chat INPUT (the user still
// reads and sends — voice never fires the turn by itself). Same contractual pattern as
// assistant-confirm-card.test.ts: the wiring is asserted over the source, the behaviour of the
// capture/transcription functions is pinned in lib/assistant-voice.test.ts, and the i18n keys are
// asserted against BOTH locales (English source + Spanish translation, ADR-0055/0199).
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const drawer = readFileSync(new URL('./AssistantDrawer.vue', import.meta.url), 'utf8');

describe('assistant voice input', () => {
  it('el drawer tiene botón de micrófono y usa las funciones REALES de captura y transcripción', () => {
    expect(drawer).toContain('startVoiceRecording');
    expect(drawer).toContain('transcribeAudio');
    expect(drawer).toContain('assistant.mic');
  });

  it('la denegación del navegador (NotAllowedError) se traduce a SU mensaje, no a un fallo genérico', () => {
    expect(drawer).toContain('NotAllowedError');
    expect(drawer).toContain('assistant.micDenied');
    expect(drawer).toContain('assistant.micFailed');
  });

  it('la transcripción cae en el INPUT (draft), nunca se auto-envía', () => {
    // The transcript joins whatever the user already typed; sending stays a human act.
    expect(drawer).toMatch(/draft\.value\s*=/);
    expect(drawer).not.toContain('autoSendTranscript');
  });

  it('las claves i18n del micrófono existen en inglés (fuente) Y en español (traducción)', () => {
    for (const locale of [en, es] as Array<{ assistant: Record<string, string> }>) {
      for (const key of ['mic', 'micStop', 'micDenied', 'micUnsupported', 'micFailed']) {
        expect(locale.assistant[key], `missing assistant.${key}`).toBeTruthy();
      }
    }
  });
});
