import type { OutputData } from '@editorjs/editorjs';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

interface Envelope<T> {
  ok?: boolean;
  data?: T;
  error?: string;
}

export interface PublicPageDefinition {
  module_id: string;
  path: string;
  title: string;
  reads: string[];
  slot?: string | null;
}

export function normalizePublicPagePath(path: string): string {
  const normalized = path.trim().replace(/^\/+|\/+$/g, '').toLowerCase();
  const valid = normalized.length > 0
    && normalized.length <= 120
    && normalized.split('/').every((segment) => /^[a-z0-9_-]+$/.test(segment));
  if (!valid) throw new Error('invalid public page path');
  return normalized;
}

function encodedPath(path: string): string {
  return normalizePublicPagePath(path).split('/').map(encodeURIComponent).join('/');
}

export async function listPublicPages(): Promise<PublicPageDefinition[]> {
  const response = await fetch(`${RUNTIME_URL}/api/public-pages`, { headers: runtimeHeaders() });
  const body = (await response.json().catch(() => ({}))) as Envelope<PublicPageDefinition[]>;
  if (!response.ok || !Array.isArray(body.data)) {
    throw new Error(body.error ?? `public pages → ${response.status}`);
  }
  return body.data;
}

export async function getPublicPage(path: string): Promise<OutputData> {
  const response = await fetch(`${RUNTIME_URL}/api/public-pages/${encodedPath(path)}`, {
    headers: runtimeHeaders(),
  });
  const body = (await response.json().catch(() => ({}))) as Envelope<OutputData>;
  if (!response.ok || !body.data) throw new Error(body.error ?? `public page → ${response.status}`);
  return body.data;
}

export async function putPublicPage(path: string, document: OutputData): Promise<void> {
  const response = await fetch(`${RUNTIME_URL}/api/public-pages/${encodedPath(path)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify(document),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as Envelope<unknown>;
    throw new Error(body.error ?? `public page PUT → ${response.status}`);
  }
}
