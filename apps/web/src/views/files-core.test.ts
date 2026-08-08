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

  it('fetches every file with the active Hub session and hands it to the ONE saver', () => {
    // The bytes always come through the runtime (`/api/media/raw`), because the bucket has no CORS
    // and the signed URL expires — so the fetch carries the session (ADR-0047/0171). Since hub#480
    // this page no longer decides what happens next: where a file lands is not the same answer in a
    // browser (download manager) as inside the installed app (there is none), and that lived in
    // four copies. `saveDownload` is the single one.
    expect(source).toContain('runtimeHeaders()');
    expect(source).toContain('saveDownload(file.name');
    expect(source).not.toContain('URL.createObjectURL');
    expect(source).not.toContain('window.open(');
  });
});
