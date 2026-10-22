// The page's colour mode (round 2026-10-22): the owner chooses light, dark or auto (`theme.mode`). The server writes
// it in `data-ep-mode` and paints auto light (`data-bs-theme="light"`), which is what a visitor without JS sees; for
// auto, this sets Bootstrap's `data-bs-theme` from the device's `prefers-color-scheme` and follows it while the page is
// open. It runs from the public bundle (no inline script under the page's CSP), also inside the editor's preview.
const DARK = '(prefers-color-scheme: dark)';

type MatchMedia = (query: string) => Pick<MediaQueryList, 'matches'> & {
  addEventListener(type: 'change', listener: (event: { matches: boolean }) => void): void;
};

export function followColourMode(
  doc: Document = document,
  matchMedia: MatchMedia | undefined = typeof window.matchMedia === 'function' ? window.matchMedia.bind(window) : undefined,
): void {
  const root = doc.documentElement;
  if (root.getAttribute('data-ep-mode') !== 'auto' || !matchMedia) return;
  const query = matchMedia(DARK);
  const paint = (dark: boolean) => root.setAttribute('data-bs-theme', dark ? 'dark' : 'light');
  paint(query.matches);
  query.addEventListener('change', (event) => paint(event.matches));
}
