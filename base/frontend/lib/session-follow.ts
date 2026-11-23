// The session is no live query: a follower beside the pane (BackgroundChrome) follows a live value that says when it
// changed and reads it again. The first answer is the state the session was read with, so only a change after it does.
import { type WatchSource, watch } from 'vue';

import { sessionChanged } from './access';

/** Reads the session again (`sessionChanged`) each time `source` changes after its first answer. */
export function readSessionAgainOnChange<T>(source: WatchSource<T | undefined>): void {
  watch(source, (next, previous) => {
    if (next !== undefined && previous !== undefined) sessionChanged();
  });
}
