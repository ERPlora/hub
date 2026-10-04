// hub#2325 — the side menu's screens are downloaded ahead of time, once the app is idle, so that a
// tap on the menu no longer depends on the network at that very instant.
import { describe, expect, it, vi } from 'vitest';
import { prefetchSections, type PrefetchSectionsIo } from './prefetch-sections';

const CHUNK_ERROR = new TypeError(
  'Failed to fetch dynamically imported module: http://localhost:5173/src/views/SettingsPage.vue',
);

type Loader = () => Promise<unknown>;

/** A router stand-in: each path resolves to ONE matched record whose view is `components[path]`. */
function ioFor(components: Record<string, unknown>, overrides: Partial<PrefetchSectionsIo> = {}) {
  const io: PrefetchSectionsIo = {
    resolve: (path) => {
      const section = path.split(/[?#]/, 1)[0];
      return { matched: section in components ? [{ components: { default: components[section] } }] : [] };
    },
    failedInApp: new Set<string>(),
    whenIdle: () => Promise.resolve(),
    ...overrides,
  };
  return io;
}

describe('prefetchSections (hub#2325)', () => {
  it('downloads the screen behind every path it is given', async () => {
    const employees = vi.fn<Loader>(() => Promise.resolve({}));
    const settings = vi.fn<Loader>(() => Promise.resolve({}));

    await prefetchSections(['/employees', '/settings'], ioFor({ '/employees': employees, '/settings': settings }));

    expect(employees).toHaveBeenCalledTimes(1);
    expect(settings).toHaveBeenCalledTimes(1);
  });

  it('waits for the app to be idle before each download, never during boot', async () => {
    const settings = vi.fn<Loader>(() => Promise.resolve({}));
    let becomeIdle: () => void = () => {};
    const whenIdle = vi.fn(() => new Promise<void>((resolve) => (becomeIdle = resolve)));

    const done = prefetchSections(['/settings'], ioFor({ '/settings': settings }, { whenIdle }));
    await Promise.resolve();
    expect(settings).not.toHaveBeenCalled();

    becomeIdle();
    await done;
    expect(whenIdle).toHaveBeenCalled();
    expect(settings).toHaveBeenCalledTimes(1);
  });

  it('downloads one screen at a time, so a till on 4G is not flooded at once', async () => {
    let finishFirst: () => void = () => {};
    const first = vi.fn<Loader>(() => new Promise((resolve) => (finishFirst = () => resolve({}))));
    const second = vi.fn<Loader>(() => Promise.resolve({}));

    const done = prefetchSections(['/first', '/second'], ioFor({ '/first': first, '/second': second }));
    await vi.waitFor(() => expect(first).toHaveBeenCalled());
    expect(second).not.toHaveBeenCalled();

    finishFirst();
    await done;
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('leaves alone a screen the router already has', async () => {
    const alreadyLoaded = { name: 'SettingsPage', render: () => null };

    await expect(prefetchSections(['/settings'], ioFor({ '/settings': alreadyLoaded }))).resolves.toBeUndefined();
  });

  it('never downloads the same screen twice in one document', async () => {
    const settings = vi.fn<Loader>(() => Promise.resolve({}));
    const io = ioFor({ '/settings': settings });

    await prefetchSections(['/settings'], io);
    await prefetchSections(['/settings', '/settings#data'], io);

    expect(settings).toHaveBeenCalledTimes(1);
  });

  it('a screen that never arrived marks its section, so the tap opens it in a fresh document (hub#2312)', async () => {
    const settings = vi.fn<Loader>(() => Promise.reject(CHUNK_ERROR));
    const files = vi.fn<Loader>(() => Promise.resolve({}));
    const io = ioFor({ '/settings': settings, '/files': files });

    await expect(prefetchSections(['/settings#data', '/files'], io)).resolves.toBeUndefined();

    expect([...io.failedInApp]).toEqual(['/settings']);
    // One failure does not stop the rest of the menu from being downloaded.
    expect(files).toHaveBeenCalledTimes(1);
  });

  it('a screen whose own code throws is NOT marked: the tap has to report that bug as it is', async () => {
    const settings = vi.fn<Loader>(() => Promise.reject(new ReferenceError('foo is not defined')));
    const io = ioFor({ '/settings': settings });

    await expect(prefetchSections(['/settings'], io)).resolves.toBeUndefined();

    expect(io.failedInApp.size).toBe(0);
  });

  it('a path the router cannot resolve does not stop the rest', async () => {
    const files = vi.fn<Loader>(() => Promise.resolve({}));
    const io = ioFor(
      { '/files': files },
      {
        resolve: (path) => {
          if (path === '/broken') throw new Error('No match');
          return { matched: [{ components: { default: files } }] };
        },
      },
    );

    await expect(prefetchSections(['/broken', '/files'], io)).resolves.toBeUndefined();
    expect(files).toHaveBeenCalledTimes(1);
  });
});
