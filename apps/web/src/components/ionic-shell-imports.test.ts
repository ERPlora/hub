import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const app = readFileSync(new URL('../App.vue', import.meta.url), 'utf8');
const appUpdate = readFileSync(new URL('./SidebarAppUpdate.vue', import.meta.url), 'utf8');
const importPanel = readFileSync(new URL('./ImportPanel.vue', import.meta.url), 'utf8');

describe('Ionic components rendered by the shell', () => {
  it('imports the upgrade-plan button used by App', () => {
    expect(app).toMatch(/\bIonButton\b/);
  });

  it('imports the item and label rendered by SidebarAppUpdate', () => {
    expect(appUpdate).toMatch(/\bIonItem\b/);
    expect(appUpdate).toMatch(/\bIonLabel\b/);
  });

  it('imports the divider rendered by the import report', () => {
    expect(importPanel).toMatch(/\bIonItemDivider\b/);
  });
});
