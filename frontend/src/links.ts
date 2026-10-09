export interface PageSummary {
  path: string;
  title: string;
  tags: string[];
}

export function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

const CODE = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/;

const stripMd = (s: string) => s.replace(/\.md$/i, "");

export function wikilinksToMarkdown(body: string): string {
  // split() with a capture group keeps code segments at odd indexes; leave those untouched
  return body
    .split(CODE)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target: string, label?: string) => {
            const t = target.trim();
            return `[${(label ?? t).trim()}](#wl=${encodeURIComponent(t)})`;
          }),
    )
    .join("");
}

export function resolveWikilink(target: string, pages: PageSummary[]): string | null {
  const t = stripMd(safeDecode(target)).split("#")[0].toLowerCase();
  const byPath = pages.find((p) => stripMd(p.path).toLowerCase() === t);
  if (byPath) return byPath.path;
  const stem = (p: PageSummary) => stripMd(p.path).split("/").pop()!.toLowerCase();
  const byName = pages.find((p) => stem(p) === t || p.title.toLowerCase() === t);
  return byName?.path ?? null;
}

export function resolveRelative(href: string, currentPath: string): string | null {
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#") || href.startsWith("//")) {
    return null;
  }
  const file = safeDecode(href.split("#")[0]);
  if (!/\.md$/i.test(file)) return null;
  const parts = currentPath.split("/").slice(0, -1);
  for (const seg of file.split("/")) {
    if (seg === "..") parts.pop();
    else if (seg !== "." && seg !== "") parts.push(seg);
  }
  return parts.join("/");
}

export const pageHref = (path: string) => "#/" + path.split("/").map(encodeURIComponent).join("/");

export function pathFromHash(hash: string): string {
  return hash.startsWith("#/") ? safeDecode(hash.slice(2)) : "";
}

export function markdownToWikilinks(md: string): string {
  return md.replace(/\[([^\]]*)\]\(#wl=([^)\s]+)\)/g, (_, label: string, enc: string) => {
    const target = safeDecode(enc);
    return label === target ? `[[${target}]]` : `[[${target}|${label}]]`;
  });
}
