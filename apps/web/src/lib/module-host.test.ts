import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const loader = readFileSync(new URL('./module-loader.ts', import.meta.url), 'utf8');
const host = readFileSync(new URL('../views/ModuleView.vue', import.meta.url), 'utf8');

describe('module host', () => {
  it('authenticates internal navigation requests', () => {
    expect(loader).toContain("import { RUNTIME_URL, runtimeHeaders } from './runtime'");
    expect(loader).toContain('headers: runtimeHeaders()');
  });

  it('ignores stale async mounts during rapid internal navigation', () => {
    expect(host).toContain('const generation = ++mountGeneration');
    expect(host).toContain('generation !== mountGeneration');
    expect(host).toContain('onBeforeUnmount');
  });

  it('recovers from a failed module load and canonicalizes retired tabs', () => {
    expect(host).toContain('@click="mount"');
    expect(host).toContain('router.replace(`/m/${moduleId}/${entry.nav.id}`)');
  });

  it('preserves complete module labels and scrolls before shrinking mobile tabs', () => {
    expect(host).toContain('class="ok-tabbar module-tabbar"');
    expect(host).toContain('scrollable');
    expect(host).toContain(':aria-label="tb.label"');
    expect(host).toContain('--ok-tabbar-min: 116px');
    expect(host).toContain('white-space: normal');
  });
});
