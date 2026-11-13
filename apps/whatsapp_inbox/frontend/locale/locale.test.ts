// The WhatsApp inbox's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper of the app uses exists, and the screens' established texts are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('whatsapp_inbox', en, es);
const { EN, ES } = CATALOGUES;

describe('whatsapp_inbox catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every status, delivery status, template category and state the server knows', () => {
    for (const status of ['open', 'pending', 'closed']) expect(EN.has(`whatsapp_inbox.status.${status}`), status).toBe(true);
    for (const status of ['received', 'sent', 'delivered', 'read', 'failed']) {
      expect(EN.has(`whatsapp_inbox.thread.messageStatus.${status}`), status).toBe(true);
    }
    for (const category of ['UTILITY', 'MARKETING', 'AUTHENTICATION']) {
      expect(EN.has(`whatsapp_inbox.templates.categories.${category}`), category).toBe(true);
    }
    for (const state of ['APPROVED', 'PENDING', 'REJECTED', 'PAUSED', 'DISABLED', 'DELETED']) {
      expect(EN.has(`whatsapp_inbox.templates.statuses.${state}`), state).toBe(true);
    }
    for (const blocked of ['not_connected', 'cap_reached', 'unconfigured']) {
      expect(EN.has(`whatsapp_inbox.composer.blocked.${blocked}`), blocked).toBe(true);
    }
  });

  it('keep the old screens’ words (the WORKBOOK’s screens)', () => {
    expect(ES.get('whatsapp_inbox.title')).toBe('Bandeja de WhatsApp');
    expect(ES.get('whatsapp_inbox.settingsTitle')).toBe('Ajustes del canal');
    expect(ES.get('whatsapp_inbox.inbox.search')).toBe('Filtrar contacto o teléfono…');
    expect(ES.get('whatsapp_inbox.inbox.empty')).toBe('Sin conversaciones.');
    expect(ES.get('whatsapp_inbox.inbox.erased')).toBe('Se han borrado los datos de este número.');
    expect(ES.get('whatsapp_inbox.conversation.erase')).toBe('Borrar datos de este número');
    expect(ES.get('whatsapp_inbox.conversation.eraseTitle')).toBe('¿Borrar los datos de este número?');
    expect(ES.get('whatsapp_inbox.conversation.eraseConfirm')).toBe('Borrar datos');
    expect(ES.get('whatsapp_inbox.conversation.loadError')).toBe('No se pudo cargar la conversación');
    expect(ES.get('whatsapp_inbox.templates.empty')).toBe('Sin plantillas.');
    expect(ES.get('whatsapp_inbox.settings.number')).toBe('Tu número');
    expect(ES.get('whatsapp_inbox.settings.templatesTitle')).toBe('Plantillas de Meta');
  });
});
