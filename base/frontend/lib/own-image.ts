// The address of an image a public page draws (a dish's photo, a business's logo): only one the business's own Hub
// serves, a path of its own or an absolute address of the page's origin. Anything else, from another site or a
// `javascript:` or `data:` address, is no image: a page without a session never loads one from elsewhere.

/** `url` when the page's own Hub serves it, else `''`. */
export function ownImageUrl(url: string, origin: string = window.location.origin): string {
  const value = url.trim();
  if (value.startsWith('/')) return value.startsWith('//') || value.startsWith('/\\') ? '' : value;
  try {
    const parsed = new URL(value);
    return ['http:', 'https:'].includes(parsed.protocol) && parsed.origin === origin ? parsed.href : '';
  } catch {
    return '';
  }
}
