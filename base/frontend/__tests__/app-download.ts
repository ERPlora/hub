// A download in a test (hub#1041): the page inside the installed app, whose bridge answers `save_download` as
// ERPlora/app does (HUB_APP-F30) — the place it saved the file, or a refusal by its code — and the files a browser
// would have saved through a link, captured instead of followed. Shared by every screen that downloads.
import { afterEach, vi } from 'vitest';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

/** Puts the page inside the installed app; `save_download` answers `answer` (a refusal when it is a string). */
export function insideTheAppSaving(answer: { path: string } | string | Record<string, never>) {
  const invoke = vi.fn<(command: string, args?: unknown) => Promise<unknown>>(async (command) => {
    if (command !== 'save_download') return undefined;
    if (typeof answer === 'string') throw answer;
    return answer;
  });
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

/** Takes the page out of the installed app again (an `afterEach`). */
export function outOfTheApp(): void {
  delete (window as TauriWindow).__TAURI__;
}

/** Ends each test of the file out of the installed app, with the spies on the browser's download restored. */
export function outOfTheAppAfterEach(): void {
  afterEach(() => {
    outOfTheApp();
    vi.restoreAllMocks();
  });
}

export interface BrowserDownload {
  /** The link's `download`: the name the browser saves it under. */
  name: string;
  href: string;
  blob: Blob;
}

/** The files the page hands the browser through a temporary link, from now on: their name and their bytes. */
export function browserDownloads(): BrowserDownload[] {
  const blobs = new Map<string, Blob>();
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
    const url = `blob:test/${blobs.size + 1}`;
    blobs.set(url, blob as Blob);
    return url;
  });
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  const saved: BrowserDownload[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    const href = this.getAttribute('href') ?? '';
    saved.push({ name: this.download, href, blob: blobs.get(href) as Blob });
  });
  return saved;
}

/** A translator for the helpers that take one, in a test: the key and, with values, the values as JSON. */
export function keyText(key: string, values?: Record<string, unknown>): string {
  return values ? `${key} ${JSON.stringify(values)}` : key;
}
