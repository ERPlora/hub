// Where to get the ERPlora app (hub#683): erplora.com's door of each system it publishes,
// always its latest build, which `base/spa.py` embeds in `hub-home` (`app_downloads`). The till's Windows first, then
// Linux and Android; no macOS, nothing is published for it (PUBLIC-F24). Offered in a browser only (`useSurface`):
// inside the installed app it would be the app offering to install itself; and never a button without its address.
import { useSurface } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

import { type HubHome, readJsonBlock } from './home';

export const APP_PLATFORMS = ['windows', 'linux', 'android'] as const;
export type AppPlatform = (typeof APP_PLATFORMS)[number];

export interface AppDownload {
  platform: AppPlatform;
  url: string;
}

export function useAppDownloads(): { downloads: AppDownload[]; offered: ComputedRef<boolean> } {
  const { isWeb } = useSurface();
  const embedded = readJsonBlock<HubHome>('hub-home')?.app_downloads ?? {};
  const downloads = APP_PLATFORMS.flatMap((platform) => (embedded[platform] ? [{ platform, url: embedded[platform] }] : []));
  return { downloads, offered: computed(() => isWeb.value && downloads.length > 0) };
}
