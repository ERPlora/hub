// A page as the hub paints it (its own file: one component per file): the page, with base's source of the action
// center running beside it as the shell runs it; `onSource` gets that source.
import type { ActionNoticeSource } from '@erplora/ui/shell';
import { type Component, defineComponent, h } from 'vue';

import { useHubActionNotices } from '../../../../base/frontend/lib/action-notices';

export function withHubNotices(page: Component, onSource: (source: ActionNoticeSource) => void): Component {
  return defineComponent({
    inheritAttrs: false,
    setup(_, { attrs }) {
      onSource(useHubActionNotices());
      return () => h(page, attrs);
    },
  });
}
