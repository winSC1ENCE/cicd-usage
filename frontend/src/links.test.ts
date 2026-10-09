import { expect, test } from "vitest";
import {
  markdownToWikilinks,
  pageHref,
  pathFromHash,
  resolveRelative,
  resolveWikilink,
  wikilinksToMarkdown,
  type PageSummary,
} from "./links";

const pages: PageSummary[] = [
  { path: "index.md", title: "Willkommen", tags: [] },
  { path: "HowTo/Beispiel.md", title: "Beispiel", tags: [] },
];

test("wikilinks become markdown links", () => {
  expect(wikilinksToMarkdown("see [[HowTo/Beispiel|Bsp]]")).toBe(
    "see [Bsp](#wl=HowTo%2FBeispiel)",
  );
});

test("wikilink resolves by path, name and title", () => {
  expect(resolveWikilink("HowTo%2FBeispiel", pages)).toBe("HowTo/Beispiel.md");
  expect(resolveWikilink("beispiel", pages)).toBe("HowTo/Beispiel.md");
  expect(resolveWikilink("Willkommen", pages)).toBe("index.md");
  expect(resolveWikilink("nope", pages)).toBeNull();
});

test("relative links resolve against the current page", () => {
  expect(resolveRelative("../index.md", "HowTo/Beispiel.md")).toBe("index.md");
  expect(resolveRelative("https://x.ch/a.md", "a.md")).toBeNull();
  expect(resolveRelative("img.png", "a.md")).toBeNull();
});

test("hash round trip", () => {
  expect(pathFromHash(pageHref("HowTo/Mein Test.md"))).toBe("HowTo/Mein Test.md");
});

test("malformed percent encoding does not throw", () => {
  expect(pathFromHash("#/100%")).toBe("100%");
  expect(resolveRelative("a%.md", "x.md")).toBe("a%.md");
  expect(resolveWikilink("%zz", pages)).toBeNull();
  expect(markdownToWikilinks("[x](#wl=%zz)")).toBe("[[%zz|x]]");
});

test("wikilinks inside code are left alone", () => {
  const body = "use `[[Seite]]` or\n\n```\n[[Block]]\n```\n\nand [[Echt]]";
  const out = wikilinksToMarkdown(body);
  expect(out).toContain("`[[Seite]]`");
  expect(out).toContain("[[Block]]");
  expect(out).toContain("[Echt](#wl=Echt)");
});
