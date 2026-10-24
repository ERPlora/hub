// The icons of the assistant's composer that the shell does not register yet (paperclip, microphone, stop, speaker;
// base/UI-REQUESTS.md asks @erplora/ui for them): baked at build time exactly as the shell bakes its non-Ionicons sets
// (`unplugin-icons`, raw compiler, `erploraVite()`), painted with `ion-icon`'s `src` as a `data:` URL — nothing is
// fetched. When the shell registers them, `HubIcon` names replace this file.
import paperclip from '~icons/lucide/paperclip';
import mic from '~icons/lucide/mic';
import square from '~icons/lucide/square';
import volume from '~icons/lucide/volume-2';

const svgUrl = (svg: string): string => `data:image/svg+xml;utf8,${svg}`;

export const ASSISTANT_ICONS = Object.freeze({
  attach: svgUrl(paperclip),
  mic: svgUrl(mic),
  stop: svgUrl(square),
  listen: svgUrl(volume),
});
