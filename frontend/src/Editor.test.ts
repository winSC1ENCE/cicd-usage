import { Editor } from "@tiptap/core";
import { expect, test } from "vitest";
import { editorExtensions, toMarkdown } from "./Editor";
import { markdownToWikilinks, wikilinksToMarkdown } from "./links";

test("wikilinks survive the editor round trip", () => {
  const source = "# Titel\n\nSiehe [[HowTo/Beispiel]] und [[Beispiel|dort]].\n\n- a\n- b\n";
  const editor = new Editor({ extensions: editorExtensions, content: wikilinksToMarkdown(source) });
  const out = toMarkdown(editor);
  expect(out).toContain("[[HowTo/Beispiel]]");
  expect(out).toContain("[[Beispiel|dort]]");
  expect(out).toContain("# Titel");
  expect(out).toMatch(/- a\n- b/);
  editor.destroy();
});

test("markdownToWikilinks reverses wikilinksToMarkdown", () => {
  const s = "x [[A B/C|label]] y [[D]]";
  expect(markdownToWikilinks(wikilinksToMarkdown(s))).toBe(s);
});
