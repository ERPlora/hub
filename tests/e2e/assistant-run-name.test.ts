// @vitest-environment node
// Each scenario run gives the business a name of its own, so two runs never share the start of the assistant's
// instructions (they begin with the business's name) and a provider's prompt cache cannot make a repeated run cheaper or
// faster than a business's first conversation.
import { describe, expect, it } from 'vitest';

import { ownName, renameSql, runBusinessName } from './assistant-run-name';

describe('runBusinessName', () => {
  it('is the business\'s own name with the run\'s id after it', () => {
    expect(runBusinessName('La Esquina', '20261120-151200-001-42')).toBe('La Esquina · 20261120-151200-001-42');
  });

  it('names a business without a name by the run alone', () => {
    expect(runBusinessName('', 'r1')).toBe('· r1');
  });

  it('does not stack ids when the name already carries one from a run that stopped early', () => {
    expect(runBusinessName('La Esquina · 20261120-101010-001-7', 'r2')).toBe('La Esquina · r2');
  });
});

describe('ownName', () => {
  it('is the name without a run\'s id, to put back at the end of the run', () => {
    expect(ownName('La Esquina · r2')).toBe('La Esquina');
    expect(ownName('La Esquina')).toBe('La Esquina');
    expect(ownName('· r2')).toBe('');
  });
});

describe('renameSql', () => {
  it('renames the business in the registry, quoting what SQL would read as the end of the text', () => {
    expect(renameSql("O'Brien · r1")).toBe("update base_hub set name = 'O''Brien · r1' where slug = 'a'");
  });

  it('refuses a name the shell would change on its way to psql', () => {
    expect(() => renameSql('Bar "El" · r1')).toThrow(/double quotes, dollars or backticks/);
    expect(() => renameSql('Bar $HOME')).toThrow(/double quotes, dollars or backticks/);
  });
});
