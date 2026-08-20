// The assistant drawer lets the user REPORT an AI answer (hub#946) — wiring, not layout.
//
// Microsoft Store policy 11.16: users must be able to report inappropriate AI-generated
// content. The hub's pattern for this kind of contract (`assistant-reads-the-query.test.ts`):
// read the SFC source and assert the contract — the action exists on assistant messages, it
// goes through the one report module, and every user-visible string travels via i18n.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const drawer = readFileSync(new URL('./AssistantDrawer.vue', import.meta.url), 'utf8');

describe('the drawer offers "report an issue" on assistant answers', () => {
  it('renders the report action with its test id, on assistant messages only', () => {
    expect(drawer).toContain('data-testid="assistant-report"');
    // The action lives inside the per-assistant-message action block: that block is gated on
    // the assistant role, so the report button never shows up on the user's own bubbles.
    // El cierre se busca A PARTIR del inicio, no desde el principio del fichero: desde que la
    // burbuja pinta markdown (hub#1043) hay un `<template v-for>` anidado —Vue idiomático— cuyo
    // `</template>` aparece ANTES, y con `indexOf` a secas el corte salía vacío y el test pasaba
    // a afirmar sobre la nada.
    const start = drawer.indexOf("m.role === 'assistant'");
    const actionsBlock = drawer.slice(start, drawer.indexOf('</template>', start));
    expect(actionsBlock).toContain('data-testid="assistant-report"');
  });

  it('never offers to report the live (streaming) bubble', () => {
    // The bubble being streamed is not a finished answer yet: reporting it would send a
    // truncated text. The template must gate the button on something stream-aware.
    expect(drawer).toMatch(/canReport\(/);
    expect(drawer).toContain('streaming.value');
  });

  it('the click goes through the one report module', () => {
    expect(drawer).toContain("from '../lib/assistant-report'");
    expect(drawer).toContain('reportAssistantMessage');
  });

  it('every user-visible string travels via i18n (source en + es, never hardcoded)', () => {
    for (const key of [
      'assistant.report',
      'assistant.reportTitle',
      'assistant.reportHint',
      'assistant.reportPlaceholder',
      'assistant.reportConfirm',
      'assistant.reportSent',
      'assistant.reportError',
    ]) {
      expect(drawer, `the SFC must use t('${key}')`).toContain(`t('${key}')`);
      const short = key.split('.')[1] as keyof typeof en.assistant;
      expect(en.assistant[short], `${key} missing in en.ts`).toBeTruthy();
      expect(es.assistant[short], `${key} missing in es.ts`).toBeTruthy();
      expect(en.assistant[short], `${key} must differ between en and es`).not.toBe(es.assistant[short]);
    }
    // Cancel reuses the assistant block's existing generic key instead of minting a new one.
    expect(drawer).toContain("t('assistant.confirmCancel')");
  });

  it('the dialog is the existing alert pattern with an optional comment box', () => {
    // Same alertController the write-confirm card already uses; the comment is one optional
    // textarea input, not a bespoke form.
    const script = drawer.slice(drawer.indexOf('<script'));
    expect(script).toMatch(/openReportDialog/);
    expect(script).toContain("type: 'textarea'");
  });

  it('success and failure each speak: a toast either way', () => {
    expect(drawer).toContain("from '../lib/toast'");
    expect(drawer).toContain("t('assistant.reportSent')");
    expect(drawer).toContain("t('assistant.reportError')");
  });
});
