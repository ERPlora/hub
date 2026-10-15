// The searches behind the task forms' pickers (`Combo` of @erplora/ui): a person of the team through
// Staff's own list (active ones, by name, with their role as hint) and an active project by code or name.
import { describe, expect, it } from 'vitest';

import { searchMembers, searchProjects } from './pickers';

function client(answer: unknown) {
  const calls: Array<[string, unknown]> = [];
  return {
    calls,
    api: {
      call: async (op: string, input: unknown) => {
        calls.push([op, input]);
        return answer;
      },
    },
  };
}

describe('task pickers', () => {
  it('asks Staff for the active people matching the text and names them with their role', async () => {
    const c = client({ rows: [{ id: 'm1', full_name: 'Ana López', role_name: 'Stylist' }, { id: 'm2', full_name: 'Bea Ruiz', role_name: null }] });
    const options = await searchMembers(c as never)(' ana ');
    expect(c.calls).toEqual([['staff.member.list', { search: 'ana', status: 'active', limit: 20 }]]);
    expect(options).toEqual([
      { id: 'm1', label: 'Ana López', hint: 'Stylist' },
      { id: 'm2', label: 'Bea Ruiz' },
    ]);
    await searchMembers(c as never)('');
    expect(c.calls[1]).toEqual(['staff.member.list', { status: 'active', limit: 20 }]);
  });

  it('asks for the active projects by name, with their code as hint', async () => {
    const c = client({ rows: [{ id: 'p1', code: 'opening', name: 'Opening' }] });
    const options = await searchProjects(c as never)('open');
    expect(c.calls).toEqual([['task.project.list', { search: 'open', is_active: true, limit: 20, sort: 'name' }]]);
    expect(options).toEqual([{ id: 'p1', label: 'Opening', hint: 'opening' }]);
  });
});
