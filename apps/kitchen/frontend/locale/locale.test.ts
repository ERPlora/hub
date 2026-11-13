// The kitchen app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a component or
// a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('kitchen', en, es);
const { EN } = CATALOGUES;

describe('kitchen catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every status, type, priority, destination, printer, tone and history action the server knows', () => {
    const domains: Array<[string, string[]]> = [
      ['status', ['pending', 'preparing', 'ready', 'served', 'cancelled']],
      ['itemStatus', ['pending', 'preparing', 'ready', 'served', 'cancelled', 'voided']],
      ['orderType', ['dine_in', 'takeaway', 'delivery']],
      ['priority', ['normal', 'rush', 'vip']],
      ['destination', ['both', 'display', 'printer']],
      ['printerUsage', ['kitchen', 'bar']],
      ['tone', ['chime', 'bell', 'buzzer']],
      [
        'action',
        ['received', 'created', 'started', 'ready', 'item_ready', 'item_recalled', 'item_voided', 'served', 'recalled', 'cancelled', 'rushed', 'unrushed', 'reprinted', 'deleted'],
      ],
    ];
    for (const [domain, values] of domains) for (const value of values) expect(EN.has(`kitchen.${domain}.${value}`), `${domain}.${value}`).toBe(true);
  });

  it('keep the old screens’ words: tabs, views, buttons, empty states and warnings', () => {
    expectWords(CATALOGUES, [
      ['kitchen.tabs.display', 'Display', 'Pantalla'],
      ['kitchen.tabs.tickets', 'Tickets', 'Comandas'],
      ['kitchen.tabs.stations', 'Stations', 'Estaciones'],
      ['kitchen.tabs.history', 'History', 'Historial'],
      ['kitchen.display.views.tickets', 'Tickets', 'Comandas'],
      ['kitchen.display.views.ready', 'Ready', 'Listas'],
      ['kitchen.display.views.allDay', 'All-Day', 'Resumen'],
      ['kitchen.display.stationAll', 'All', 'Todas'],
      ['kitchen.display.stationNone', 'No station', 'Sin estación'],
      ['kitchen.display.fullscreen', 'Full screen', 'Pantalla completa'],
      ['kitchen.display.exitFullscreen', 'Exit full screen', 'Salir de pantalla completa'],
      ['kitchen.display.emptyTickets', 'No tickets on the line.', 'No hay comandas en marcha.'],
      ['kitchen.display.emptyReady', 'Nothing waiting to be picked up.', 'No hay nada esperando a recoger.'],
      ['kitchen.display.emptyAllDay', 'Nothing left to cook.', 'No queda nada por cocinar.'],
      ['kitchen.display.loadError', 'Could not load the kitchen display', 'No se pudo cargar la pantalla de cocina'],
      ['kitchen.display.passPrintFailed', 'The pass could not be printed. Check the printer of the station.', 'No se ha podido imprimir el pase. Revisa la impresora de la estación.'],
      [
        'kitchen.display.rushNoticeFailed',
        'The urgent notice could not be printed. Tell the kitchen by voice and check its printer.',
        'No se ha podido imprimir el aviso de urgencia. Avisa a cocina de viva voz y revisa su impresora.',
      ],
      ['kitchen.card.waiter', 'Waiter: {name}', 'Camarero: {name}'],
      ['kitchen.card.round', 'Round {n}', 'Ronda {n}'],
      ['kitchen.card.bump', 'Ready', 'Listo'],
      ['kitchen.card.markRush', 'Mark rush', 'Marcar urgente'],
      ['kitchen.card.clearRush', 'Remove rush', 'Quitar urgente'],
      ['kitchen.card.recall', 'Recall', 'Recuperar'],
      ['kitchen.card.served', 'Served', 'Servida'],
      ['kitchen.card.voided', 'Voided', 'Anulado'],
      ['kitchen.tickets.search', 'Search ticket or destination…', 'Buscar comanda o destino…'],
      ['kitchen.tickets.empty', 'No tickets.', 'Sin comandas.'],
      ['kitchen.tickets.new', 'New ticket', 'Nueva comanda'],
      ['kitchen.tickets.actions.start', 'Fire', 'Lanzar'],
      ['kitchen.form.submit', 'Create ticket', 'Crear comanda'],
      ['kitchen.stations.search', 'Search station…', 'Buscar estación…'],
      ['kitchen.stations.empty', 'No stations.', 'Sin estaciones.'],
      ['kitchen.stations.add', 'Add station', 'Añadir estación'],
      ['kitchen.stations.form.namePlaceholder', 'e.g. Grill', 'p. ej. Plancha'],
      ['kitchen.stations.form.create', 'Create station', 'Crear estación'],
      ['kitchen.stations.delete.title', 'Delete «{name}»?', '¿Eliminar «{name}»?'],
      [
        'kitchen.stations.delete.message',
        'The station leaves the list and stops receiving tickets. Tickets already sent keep it in their history.',
        'La estación sale de la lista y deja de recibir comandas. Las comandas ya enviadas la conservan en su historial.',
      ],
      ['kitchen.routing.submit', 'Save routing', 'Guardar enrutado'],
      ['kitchen.history.title', 'Kitchen history', 'Historial de cocina'],
      ['kitchen.history.search', 'Search ticket or notes…', 'Buscar comanda o notas…'],
      ['kitchen.history.empty', 'No recent kitchen activity.', 'Sin actividad reciente en cocina.'],
      ['kitchen.settings.showTimer', 'Show timer', 'Mostrar cronómetro'],
      ['kitchen.settings.warning', 'Amber warning (minutes)', 'Aviso ámbar (minutos)'],
      ['kitchen.settings.critical', 'Red alert (minutes)', 'Aviso rojo (minutos)'],
      ['kitchen.settings.worksFromScreen', 'The kitchen works from the screen', 'La cocina trabaja con la pantalla'],
    ]);
  });
});
