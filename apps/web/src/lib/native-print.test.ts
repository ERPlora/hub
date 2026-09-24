import { afterEach, describe, expect, it, vi } from 'vitest';
import { NATIVE_PRINT_COMMAND, printDocumentNatively } from './native-print';

// hub#2006 — the page holds the A4 html, the shell holds the system print dialog. The contract is the
// command name and its argument; the Rust half is pinned by `apps/tauri/src-tauri/tests/native_print.rs`.

afterEach(() => vi.unstubAllGlobals());

describe('printDocumentNatively', () => {
  it('asks the shell to open the system print dialog with the document', async () => {
    const invoke = vi.fn(async () => null);
    vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });

    await printDocumentNatively('<p>F-1</p>');

    expect(NATIVE_PRINT_COMMAND).toBe('print_document');
    expect(invoke).toHaveBeenCalledWith('print_document', { html: '<p>F-1</p>' });
  });

  it('rejects with the shell refusal so the door can take another route', async () => {
    const invoke = vi.fn(async () => { throw 'native_print_unsupported'; });
    vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });

    await expect(printDocumentNatively('<p>F-1</p>')).rejects.toThrow(/native_print_unsupported/);
  });

  it('rejects outside the installed app: there is no shell to ask', async () => {
    vi.stubGlobal('window', {});

    await expect(printDocumentNatively('<p>F-1</p>')).rejects.toThrow(/native_print_unavailable/);
  });
});
