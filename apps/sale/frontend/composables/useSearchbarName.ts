// `useSearchbarName(bar, hint)`: names a searchbar of the app by its hint, in the person's language. Ionic 8
// names the inner input of an `ion-searchbar` «search text», in English, whatever its hint says
// (outfitkit#182), so a screen reader would read that instead of «Buscar producto…». `bar` is the template
// ref of the `IonSearchbar`; the shared `syncSearchbarInputName` names the first searchbar under the root it
// gets (its parent here), after the render: once it is on screen, again when the hint changes (the
// language, the territory's tax) and when the searchbar is created again.
import { syncSearchbarInputName } from '@erplora/ui/components';
import { type ShallowRef, watch } from 'vue';

export function useSearchbarName(bar: Readonly<ShallowRef<{ $el: Element } | null>>, hint: () => string): void {
  watch([bar, hint], ([searchbar]) => syncSearchbarInputName(searchbar?.$el.parentElement, hint), { flush: 'post' });
}
