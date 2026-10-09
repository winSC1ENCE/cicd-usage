import { EditorContent, useEditor } from "@tiptap/react";
import Link from "@tiptap/extension-link";
import StarterKit from "@tiptap/starter-kit";
import Table from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import { Markdown } from "tiptap-markdown";
import { markdownToWikilinks, wikilinksToMarkdown } from "./links";

export const editorExtensions = [
  StarterKit,
  Link.configure({ openOnClick: false }),
  Table,
  TableRow,
  TableHeader,
  TableCell,
  Markdown.configure({ html: false, linkify: false }),
];

export function toMarkdown(editor: { storage: Record<string, unknown> }): string {
  const md = (editor.storage.markdown as { getMarkdown(): string }).getMarkdown();
  return markdownToWikilinks(md);
}

interface Props {
  initialBody: string;
  busy: boolean;
  onSave: (body: string) => void;
  onDirty?: () => void;
  onCancel: () => void;
}

export function Editor({ initialBody, busy, onSave, onDirty, onCancel }: Props) {
  const editor = useEditor({
    extensions: editorExtensions,
    content: wikilinksToMarkdown(initialBody),
    onUpdate: () => onDirty?.(),
  });
  if (!editor) return null;

  const btn = (label: string, active: boolean, run: () => void) => (
    <button type="button" className={active ? "on" : ""} onClick={run} aria-pressed={active}>
      {label}
    </button>
  );
  const chain = () => editor.chain().focus();

  return (
    <div className="editor">
      <div className="toolbar" role="toolbar" aria-label="Formatierung">
        {btn("B", editor.isActive("bold"), () => chain().toggleBold().run())}
        {btn("I", editor.isActive("italic"), () => chain().toggleItalic().run())}
        {btn("H1", editor.isActive("heading", { level: 1 }), () =>
          chain().toggleHeading({ level: 1 }).run(),
        )}
        {btn("H2", editor.isActive("heading", { level: 2 }), () =>
          chain().toggleHeading({ level: 2 }).run(),
        )}
        {btn("H3", editor.isActive("heading", { level: 3 }), () =>
          chain().toggleHeading({ level: 3 }).run(),
        )}
        {btn("• Liste", editor.isActive("bulletList"), () => chain().toggleBulletList().run())}
        {btn("1. Liste", editor.isActive("orderedList"), () => chain().toggleOrderedList().run())}
        {btn("Zitat", editor.isActive("blockquote"), () => chain().toggleBlockquote().run())}
        {btn("Code", editor.isActive("codeBlock"), () => chain().toggleCodeBlock().run())}
        {btn("Tabelle", false, () =>
          chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
        )}
        {btn("Link", editor.isActive("link"), () => {
          const url = window.prompt("URL oder Seitenlink (z.B. ../index.md)");
          if (url === null) return;
          if (url === "") chain().unsetLink().run();
          else chain().setLink({ href: url }).run();
        })}
      </div>
      <EditorContent editor={editor} className="prose" />
      <div className="actions">
        <button type="button" className="primary" disabled={busy} onClick={() => onSave(toMarkdown(editor))}>
          {busy ? "Speichere…" : "Als Merge Request speichern"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel}>
          Abbrechen
        </button>
      </div>
    </div>
  );
}
