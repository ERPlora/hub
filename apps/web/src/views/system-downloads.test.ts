// What the System screen may offer to download, and to whom (hub#480).
//
// Three `window.open` calls survived ADR-0255 and two of them lived here. Counted against the code
// that feeds them, they were not three equal cases at all:
//
//  * **The installer, three buttons (Windows / Linux / Android).** Reachable, and a no-op inside the
//    installed app — where it is also the app offering to install itself.
//  * **The document download, one row action.** Not reachable at ALL: `crates/server/src/system.rs`
//    builds every document with `"url": Value::Null`, and the action is `disabled: (row) => !row.url`.
//    It has been a permanently greyed-out button on every row since it was written.
//
// So the fix is not the same for the two. This file pins both, on the source, because neither shows
// up in a type error and both are one careless line away from coming back.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./SystemPage.vue', import.meta.url), 'utf8');

describe('the installer offer', () => {
  it('leaves through the ONE door out of the till, not window.open', () => {
    // `window.open` opens nothing inside the webview of the installed app; `openExternal` knows the
    // difference between the two surfaces and rejects when the trip cannot be made (ADR-0255).
    expect(source).toContain('openExternal(bridgeDownloadUrl(os.platform))');
    expect(source).not.toContain('window.open(');
  });

  it('is not shown to the app that would be installing itself', () => {
    // Inside `com.erplora.app` this card is the app offering its own installer. Updating it is its
    // own job (hub#400), and the printer steps above already drop «download» and «install».
    expect(source).toContain('v-if="!bridge.online && !inInstalledApp"');
    expect(source).toContain('printerSetupStepKeys(inInstalledApp)');
  });

  it('says so when the browser could not be reached', () => {
    // The toast used to fire BEFORE the window.open that did nothing: it announced a download that
    // never started. Now the announcement waits for the trip, and a failure has its own sentence.
    expect(source).toContain("showToast(t('download.failed'))");
  });
});

describe('the documents tab', () => {
  it('does not offer a download the runtime can never enable', () => {
    // `system.rs` sends `"url": null` for every document, so this action was disabled on every row,
    // forever — a button that promises something the API does not carry. The fix for a promise
    // nothing can keep is to stop making it, not to wire it to a helper it will never call.
    expect(source).not.toContain('disabled: (row) => !row.url');
    expect(source).not.toContain("actionId === 'download'");
    // And nothing here fetches a document behind the user's back either.
    expect(source).not.toContain('URL.createObjectURL');
  });
});
