// What the approval dialog says is being approved (hub#579).
//
// The manager was approving BLIND: the dialog printed «Se necesita la aprobación de un encargado»
// and nothing else — not the action, not even which app asked. hub#363 refused to print the
// permission key or the command name on purpose («those are our vocabulary, not the counter's»),
// and that decision stands: the answer is not to leak `sales.void`, it is to say it in the words
// of the business.
//
// Every POS that asks for a manager says WHAT: Toast, Square and Lightspeed all name the action on
// the approval prompt. A prompt that does not is a rubber stamp — and the whole point of the
// receipt (`approved_by`) is that somebody decided something specific.
//
// The ladder, best first: the module's own translation of that command → the module's localised
// name → a generic sentence. Never the raw command: falling back to `sales.void` would undo the
// hub#363 decision at exactly the moment the cashier is watching.
import { describe, expect, it } from 'vitest';

import { describeElevation } from './elevation-label';

const catalogue = [
  {
    moduleId: 'sales',
    moduleName: 'Ventas / TPV',
    commands: { 'sales.void': { label: 'Anular una venta' } },
  },
];

describe('the dialog says what is being approved', () => {
  it('uses the command label the module translated', () => {
    expect(describeElevation({ command: 'sales.void' }, catalogue)).toEqual({
      action: 'Anular una venta',
      moduleName: 'Ventas / TPV',
    });
  });

  it('falls back to the localised MODULE name when the command has no label', () => {
    // Better a true half-answer («something in Ventas / TPV») than our internal vocabulary.
    expect(describeElevation({ command: 'sales.discount' }, catalogue)).toEqual({
      action: '',
      moduleName: 'Ventas / TPV',
    });
  });

  it('never leaks the command or the permission when the module is unknown', () => {
    const described = describeElevation(
      { command: 'unknown_module.do_thing', permission: 'unknown_module.change_thing' },
      catalogue,
    );
    expect(described).toEqual({ action: '', moduleName: '' });
    expect(JSON.stringify(described)).not.toContain('do_thing');
    expect(JSON.stringify(described)).not.toContain('change_thing');
  });

  it('is not fooled by a command whose module prefix repeats a dot', () => {
    expect(describeElevation({ command: 'sales.orders.void' }, catalogue).moduleName).toBe(
      'Ventas / TPV',
    );
  });
});
