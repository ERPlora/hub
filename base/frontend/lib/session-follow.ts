// A follower beside the pane (BackgroundChrome) follows a live value and acts when it changes. The first answer is the
// state the page was opened with (the session it read, the appearance its way in painted), so only a change after it
// does. The session is no live query: a change of what it says is followed by reading it again.
import { type WatchSource, watch } from 'vue';

import { sessionChanged } from './access';

/** Runs `act` each time `source` changes after its first answer. */
export function onChangeAfterFirstAnswer<T>(source: WatchSource<T | undefined>, act: () => void): void {
  watch(source, (next, previous) => {
    if (next !== undefined && previous !== undefined) act();
  });
}

/** Reads the session again (`sessionChanged`) each time `source` changes after its first answer. */
export function readSessionAgainOnChange<T>(source: WatchSource<T | undefined>): void {
  onChangeAfterFirstAnswer(source, () => sessionChanged());
}
