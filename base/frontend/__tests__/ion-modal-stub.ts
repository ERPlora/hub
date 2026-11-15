// `@ionic/vue` with its inline `IonModal` swapped for the test double of `@erplora/ui` (an overlay presents itself only
// in a real browser), so every modal of the tree opens in the test. `vi.mock` is hoisted above the file's imports, so its
// factory reaches this module through a dynamic import:
//
//   vi.mock('@ionic/vue', async (importOriginal) => (await import('<path>/ion-modal-stub')).ionicWithModalStub(importOriginal));
export async function ionicWithModalStub(importOriginal: () => Promise<unknown>): Promise<Record<string, unknown>> {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...((await importOriginal()) as object), IonModal: IonModalStub };
}
