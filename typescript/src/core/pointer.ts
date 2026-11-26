/** RFC 6901 JSON Pointer helpers. */

export const escapeToken = (t: string): string => t.replace(/~/g, "~0").replace(/\//g, "~1");
export const unescapeToken = (t: string): string => t.replace(/~1/g, "/").replace(/~0/g, "~");

export function join(base: string, ...tokens: (string | number)[]): string {
  return base + tokens.map((t) => "/" + escapeToken(String(t))).join("");
}

export function split(pointer: string): string[] {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) throw new Error(`JSON Pointer must start with '/': ${JSON.stringify(pointer)}`);
  return pointer.slice(1).split("/").map(unescapeToken);
}

export function decodeFragment(fragment: string): string[] {
  const frag = fragment.startsWith("#") ? fragment.slice(1) : fragment;
  return split(decodeURIComponent(frag));
}
