import { ref } from 'vue';
import { applyUserLocale } from '../i18n';
import { hubSettings } from './hub-settings';
import { RUNTIME_URL, runtimeHeaders } from './runtime';
import { setUser, user } from './session';
import {
  applyUserThemePreferences,
  type ThemeMode,
  type ThemePalette,
} from './theme';

export interface UserPreferences {
  language: string | null;
  theme_mode: ThemeMode | null;
  theme_palette: ThemePalette | null;
}

export interface UserProfile {
  id: string;
  name: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  permissions: string[];
  cloud_user_id: string | null;
  avatar_url: string | null;
  preferences: UserPreferences;
}

export const currentUserProfile = ref<UserProfile | null>(null);
let avatarObjectUrl: string | null = null;

async function responseError(response: Response, fallback: string): Promise<Error> {
  const body = (await response.json().catch(() => null)) as
    | { error?: string | { message?: string } }
    | null;
  const message =
    typeof body?.error === 'string'
      ? body.error
      : body?.error?.message;
  return new Error(message || fallback);
}

async function avatarUrl(profile: UserProfile, force = false): Promise<string | null> {
  if (!profile.avatar_url) return null;
  if (avatarObjectUrl && !force) return avatarObjectUrl;
  const response = await fetch(`${RUNTIME_URL}${profile.avatar_url}?v=${Date.now()}`, {
    headers: runtimeHeaders(),
  });
  if (!response.ok) return null;
  const next = URL.createObjectURL(await response.blob());
  if (avatarObjectUrl) URL.revokeObjectURL(avatarObjectUrl);
  avatarObjectUrl = next;
  return next;
}

function applyPreferences(profile: UserProfile): void {
  const hubLanguage = hubSettings.value?.language ?? 'es';
  const hubPalette = hubSettings.value?.theme_palette ?? 'erplora';
  applyUserLocale(profile.preferences.language, hubLanguage);
  applyUserThemePreferences(
    profile.preferences.theme_mode,
    profile.preferences.theme_palette,
    hubPalette,
  );
}

async function applyProfile(profile: UserProfile, refreshAvatar = false): Promise<UserProfile> {
  currentUserProfile.value = profile;
  applyPreferences(profile);
  const ownAvatar = await avatarUrl(profile, refreshAvatar).catch(() => null);
  const previousAvatar = user.value?.avatarUrl;
  setUser({
    id: profile.id,
    cloudUserId: profile.cloud_user_id,
    name: profile.name,
    email: profile.email,
    avatarUrl:
      ownAvatar ??
      (previousAvatar && !previousAvatar.startsWith('blob:') ? previousAvatar : null),
    role: profile.role,
    permissions: profile.permissions,
  });
  return profile;
}

export async function getUserProfile(): Promise<UserProfile> {
  const response = await fetch(`${RUNTIME_URL}/api/profile`, { headers: runtimeHeaders() });
  if (!response.ok) throw new Error(`profile → ${response.status}`);
  return applyProfile((await response.json()) as UserProfile);
}

export async function updateUserProfile(
  input: Pick<UserProfile, 'first_name' | 'last_name' | 'email' | 'preferences'>,
): Promise<UserProfile> {
  const response = await fetch(`${RUNTIME_URL}/api/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw await responseError(response, `profile PUT → ${response.status}`);
  }
  return applyProfile((await response.json()) as UserProfile);
}

/** Persiste las preferencias actuales conservando la identidad del perfil. */
export async function updateUserPreferences(preferences: UserPreferences): Promise<UserProfile> {
  const profile = currentUserProfile.value ?? (await getUserProfile());
  return updateUserProfile({
    first_name: profile.first_name,
    last_name: profile.last_name,
    email: profile.email,
    preferences,
  });
}

export async function uploadUserAvatar(file: File): Promise<UserProfile> {
  const form = new FormData();
  form.append('avatar', file);
  const response = await fetch(`${RUNTIME_URL}/api/profile/avatar`, {
    method: 'POST',
    headers: runtimeHeaders(),
    body: form,
  });
  if (!response.ok) {
    throw await responseError(response, `avatar → ${response.status}`);
  }
  return applyProfile((await response.json()) as UserProfile, true);
}

export async function deleteUserAvatar(): Promise<UserProfile> {
  const response = await fetch(`${RUNTIME_URL}/api/profile/avatar`, {
    method: 'DELETE',
    headers: runtimeHeaders(),
  });
  if (!response.ok) throw new Error(`avatar DELETE → ${response.status}`);
  if (avatarObjectUrl) {
    URL.revokeObjectURL(avatarObjectUrl);
    avatarObjectUrl = null;
  }
  const profile = (await response.json()) as UserProfile;
  setUser({ ...user.value!, avatarUrl: null });
  currentUserProfile.value = profile;
  return profile;
}

export function resetUserProfile(): void {
  currentUserProfile.value = null;
  if (avatarObjectUrl) URL.revokeObjectURL(avatarObjectUrl);
  avatarObjectUrl = null;
}
