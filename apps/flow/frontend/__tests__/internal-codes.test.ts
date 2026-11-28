// The detector the tests of Automations share: what a screen must never show a person, and what it may.
import { describe, expect, it } from 'vitest';

import type { CatalogOut } from '../operations';
import { catalogNames, internalCodesIn } from './internal-codes';

const CATALOG = {
  off_apps: [],
  events: [{ name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' }],
  actions: [
    {
      name: 'task.task.create',
      kind: 'command',
      app: 'task',
      app_name: 'Tasks',
      description: '',
      outputs: [],
      fields: [
        { name: 'title', type: 'string', required: true, description: '', choices: [] },
        { name: 'priority', type: 'choice', required: false, description: '', choices: ['low', 'medium', 'high', 'urgent'] },
      ],
    },
  ],
} as CatalogOut;
const NAMES = catalogNames(CATALOG);

describe('internal codes on a screen of Automations', () => {
  it('finds the name an operation or an event has inside the Hub', () => {
    expect(internalCodesIn('It tried to do «task.task.create», so it stopped.', NAMES)).toEqual(['task.task.create']);
    expect(internalCodesIn('When sale.sale.completed', NAMES)).toEqual(['sale.sale.completed']);
  });

  it('finds the id of a step, a name in snake case and the name of a permission to call', () => {
    expect(internalCodesIn('s4: It could not reach «qa.invalid», so it stopped.', NAMES)).toEqual(['s4']);
    expect(internalCodesIn('Whatsapp inbox · whatsapp_inbox.conversation.list', NAMES)).toEqual(['whatsapp_inbox.conversation.list']);
    expect(internalCodesIn('Status in_progress', NAMES)).toEqual(['in_progress']);
    expect(internalCodesIn('Allow http:https://api.example.com', NAMES)).toEqual(['http:https://']);
  });

  it('finds the values of a list written as they are kept', () => {
    expect(internalCodesIn('Priority low, medium, high, urgent', NAMES)).toEqual(['low, medium, high, urgent']);
  });

  it('lets through what a person reads: names, hosts, numbers and amounts', () => {
    const said = 'Did: Create a task · Call api.example.com: it answered 201 · Priority: Low, Medium, High, Urgent · 12,50 € · Step 4';
    expect(internalCodesIn(said, NAMES)).toEqual([]);
    expect(internalCodesIn('Hizo: Crear una tarea · Llamar a qa-cumple.invalid · Prioridad: Alta · E2E FlowWords 390 m4x2', NAMES)).toEqual([]);
  });
});
