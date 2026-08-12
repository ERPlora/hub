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

  it('turns a drag & drop into a move, and unsubscribes from it like every other event', () => {
    // The drag lives in the Web Component (`ok-file-manager`, OutfitKit ≥ 0.1.36); the page only
    // hears `ok-move` and calls the endpoint (hub#710/#741). Three separate lines have to survive
    // for a drop to do anything, and nothing was watching them: a release batch squashed from a
    // stale branch already reverted this file's download path once without a check going red.
    // A listener added and never removed also leaks across route changes, so both halves count.
    expect(source).toContain("addEventListener('ok-move'");
    expect(source).toContain("removeEventListener('ok-move'");
    expect(source).toContain('moveMedia(from, to)');
  });
});
