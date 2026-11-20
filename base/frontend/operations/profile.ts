// Types of base/schemas/profile.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

export type ProfileLanguage = '' | 'es' | 'en';
export type ProfileThemeMode = '' | 'system' | 'light' | 'dark';
export type ProfileUiScale = 80 | 90 | 100 | 110 | 120;

/** `base.ProfileOut`: «My profile». Empty language, mode or palette: the business's. */
export interface Profile {
  first_name: string;
  last_name: string;
  contact_email: string;
  avatar_url: string;
  language: ProfileLanguage;
  theme_mode: ProfileThemeMode;
  palette: string;
  ui_scale: ProfileUiScale;
  role: string;
  has_pin: boolean;
  pin_length: number;
}

/** `base.PreferencesIn` / `PreferencesOut`. */
export interface Preferences {
  language: ProfileLanguage;
  theme_mode: ProfileThemeMode;
  palette: string;
  ui_scale: ProfileUiScale;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.profile.get': { input: NoInput; output: Profile };
    'base.profile.update': { input: { first_name: string; last_name: string; contact_email: string }; output: Profile };
    'base.profile.preferences_set': { input: Preferences; output: Preferences };
    'base.profile.avatar_set': {
      input: { content_type: 'image/jpeg' | 'image/png' | 'image/webp'; data_base64: string };
      output: { avatar_url: string };
    };
    'base.profile.avatar_remove': { input: NoInput; output: { avatar_url: string } };
  }
}
