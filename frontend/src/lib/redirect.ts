/**
 * Sanitizes an internal `next` redirect path to prevent open redirects.
 * Accepts only same-origin relative paths starting with a single "/",
 * with no "//", no backslash, and no scheme or host.
 */
export function sanitizeNextPath(raw: string | null | undefined): string {
  if (!raw) return '/';
  const trimmed = raw.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) {
    return '/';
  }
  if (trimmed.includes('\\') || /[\u0000-\u001f\u007f]/.test(trimmed)) {
    return '/';
  }
  const pathPart = trimmed.split(/[?#]/, 1)[0];
  if (pathPart.includes(':')) {
    return '/';
  }
  try {
    const parsed = new URL(trimmed, 'http://beanbox.invalid');
    if (
      parsed.origin !== 'http://beanbox.invalid' ||
      !parsed.pathname.startsWith('/') ||
      parsed.pathname.startsWith('//')
    ) {
      return '/';
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return '/';
  }
}
