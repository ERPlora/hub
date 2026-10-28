// What the customer app's searchbars are named with. Ionic 8 names the inner input of an `ion-searchbar`
// «search text», in English (outfitkit#182), so every searchbar of the app is named by its hint through
// `@erplora/ui/components`' `syncSearchbarInputName` (happy-dom never renders that input: the helper's own
// effect is tested in `ui`, and seen in the e2e). A test mocks that helper with `recordSearchbarName`,
// which writes down, at each call, the searchbar the helper names (the first one under the root it gets)
// and the name it reads then:
//   vi.mock('@erplora/ui/components', async (importOriginal) => ({
//     ...(await importOriginal<typeof import('@erplora/ui/components')>()),
//     syncSearchbarInputName: (await import('<path>/__tests__/searchbar-name')).recordSearchbarName,
//   }));
const given: { bar: Element | null; name: string }[] = [];

export function recordSearchbarName(root: ParentNode | null | undefined, name: () => string): void {
  given.push({ bar: root?.querySelector('ion-searchbar') ?? null, name: name() });
}

/** The names `bar` was given, in order (the one it reads now, last). */
export function namesGiven(bar: Element | null | undefined): string[] {
  return given.filter((entry) => entry.bar !== null && entry.bar === bar).map((entry) => entry.name);
}
