import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./FilesPage.vue', import.meta.url), 'utf8');

describe('Files core interactions', () => {
  it('uses accessible Ionic dialogs instead of browser-native prompts', () => {
    expect(source).toContain('alertController.create');
    expect(source).not.toContain('window.confirm');
    expect(source).not.toContain('window.prompt');
  });

  it('distinguishes a load failure from an empty folder', () => {
    expect(source).toContain('loadFailed');
    expect(source).toContain("t('files.loadErrorTitle')");
  });

  it('fetches protected local files with the active Hub session', () => {
    expect(source).toContain('runtimeHeaders()');
    expect(source).toContain('URL.createObjectURL');
    expect(source).not.toContain('window.open(href');
  });
});
