// tasks#45 · «My tasks» lists only OPEN tasks, so the one just completed vanished on the next result and
// the next card slid into its slot. It stays where it was, shown as done, until the person leaves the
// tab (Things, Apple Reminders, Asana): the fresh rows keep the server's order and each kept task goes
// back right after the card that preceded it. A kept task the server lists again (reopened) is painted
// from the server, once.

export function keepCompletedInPlace<T extends { id: string }>(previous: readonly T[], fresh: readonly T[], kept: ReadonlyMap<string, T>): T[] {
  const result = [...fresh];
  const has = (id: string): boolean => result.some((r) => r.id === id);
  previous.forEach((row, i) => {
    const done = kept.get(row.id);
    if (!done || has(row.id)) return;
    let at = 0;
    for (let j = i - 1; j >= 0; j--) {
      const k = result.findIndex((r) => r.id === previous[j].id);
      if (k >= 0) {
        at = k + 1;
        break;
      }
    }
    result.splice(at, 0, done);
  });
  return result;
}
