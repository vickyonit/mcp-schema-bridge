/** Python urllib.parse.urljoin / urldefrag semantics (for identical $id / $ref resolution). */
const USES_RELATIVE = new Set(["", "ftp", "http", "gopher", "nntp", "imap", "wais", "file", "https", "shttp", "mms", "prospero", "rtsp", "rtsps", "rtspu", "sftp", "svn", "svn+ssh", "ws", "wss"]);
const schemeOf = (u: string): string => /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(u)?.[1]?.toLowerCase() ?? "";

export function urljoin(base: string, url: string): string {
  if (!base) return url;
  if (!url) return base;
  const bscheme = schemeOf(base);
  const scheme = schemeOf(url) || bscheme;
  if (scheme !== bscheme || !USES_RELATIVE.has(scheme)) return url;
  try {
    return new URL(url, base).href;
  } catch {
    return url;
  }
}

export function urldefrag(url: string): [string, string] {
  const i = url.indexOf("#");
  return i === -1 ? [url, ""] : [url.slice(0, i), url.slice(i + 1)];
}
