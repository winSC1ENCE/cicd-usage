import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { Editor } from "./Editor";
import { GraphView } from "./GraphView";
import {
  pageHref,
  pathFromHash,
  resolveRelative,
  resolveWikilink,
  wikilinksToMarkdown,
  type PageSummary,
} from "./links";

export type { PageSummary };

interface Page extends PageSummary {
  body: string;
  backlinks: string[];
}

interface SearchHit {
  path: string;
  title: string;
  snippet: string;
}

interface Draft {
  path: string;
  body: string;
  exists: boolean;
}

interface Notice {
  kind: "ok" | "error";
  text: string;
  url?: string;
}

function storedAuthor(): string {
  try {
    return localStorage.getItem("wiki-author") ?? "";
  } catch {
    return "";
  }
}

const DISCARD_PROMPT = "Ungespeicherte Änderungen verwerfen?";

function useHashPath(canLeave: () => boolean): string {
  const [path, setPath] = useState(() => pathFromHash(window.location.hash));
  const accepted = useRef(window.location.hash);
  const guard = useRef(canLeave);
  guard.current = canLeave;
  useEffect(() => {
    const onChange = () => {
      const hash = window.location.hash;
      if (hash !== accepted.current && !guard.current()) {
        window.location.hash = accepted.current;
        return;
      }
      accepted.current = hash;
      setPath(pathFromHash(hash));
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return path;
}

function groupByFolder(pages: PageSummary[]): [string, PageSummary[]][] {
  const groups = new Map<string, PageSummary[]>();
  for (const p of pages) {
    const folder = p.path.includes("/") ? p.path.split("/").slice(0, -1).join(" / ") : "";
    groups.set(folder, [...(groups.get(folder) ?? []), p]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export function App() {
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [editable, setEditable] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [lastViewed, setLastViewed] = useState("");
  const dirty = useRef(false);
  const hashPath = useHashPath(() => !dirty.current || window.confirm(DISCARD_PROMPT));
  const showGraph = hashPath === "graph";
  const current = (showGraph ? "" : hashPath) || (pages.find((p) => p.path === "index.md") ?? pages[0])?.path || "";

  useEffect(() => {
    fetch("/api/pages")
      .then((r) => r.json())
      .then(setPages)
      .catch(() => setPages([]));
  }, [reloadKey]);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((c) => setEditable(Boolean(c.editable)))
      .catch(() => setEditable(false));
  }, []);

  useEffect(() => setDraft(null), [current, showGraph]);
  useEffect(() => {
    dirty.current = false;
  }, [draft]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty.current) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
  useEffect(() => {
    if (!showGraph && current) setLastViewed(current);
  }, [showGraph, current]);

  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    fetch("/api/pages/" + current.split("/").map(encodeURIComponent).join("/"))
      .then((r) => {
        if (!r.ok) throw new Error("Seite nicht gefunden");
        return r.json();
      })
      .then((p: Page) => {
        if (cancelled) return;
        setPage(p);
        setError(null);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setPage(null);
        setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [current, reloadKey]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    const timer = setTimeout(() => {
      fetch("/api/search?q=" + encodeURIComponent(query.trim()))
        .then((r) => (r.ok ? r.json() : []))
        .then(setHits)
        .catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  const askAuthor = (): string | null => {
    let author = storedAuthor();
    if (!author) {
      author = (window.prompt("Dein Name (erscheint im Merge Request)") ?? "").trim();
      if (!author) return null;
      try {
        localStorage.setItem("wiki-author", author);
      } catch {
        /* storage unavailable */
      }
    }
    return author;
  };

  const send = async (method: "PUT" | "DELETE", path: string, payload: object) => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await fetch("/api/pages/" + path.split("/").map(encodeURIComponent).join("/"), {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : `Fehler ${r.status}`);
      if (data.merge_request) {
        setNotice({ kind: "ok", text: "Merge Request erstellt:", url: data.merge_request });
      } else {
        setNotice({ kind: "ok", text: data.message ?? "Gespeichert" });
        setReloadKey((k) => k + 1);
        if (method === "DELETE") window.location.hash = "#/";
      }
      setDraft(null);
    } catch (e) {
      setNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const save = (body: string) => {
    if (!draft) return;
    const author = askAuthor();
    if (!author) return;
    const stem = draft.path.replace(/\.md$/, "").split("/").pop();
    void send("PUT", draft.path, { body, author, ...(draft.exists ? {} : { title: stem }) });
  };

  const remove = () => {
    if (!page || !window.confirm(`"${page.title}" per Merge Request löschen?`)) return;
    const author = askAuthor();
    if (author) void send("DELETE", page.path, { author });
  };

  const newPage = () => {
    if (dirty.current && !window.confirm(DISCARD_PROMPT)) return;
    const input = window.prompt("Pfad der neuen Seite, z.B. HowTo/Neue Seite");
    if (!input) return;
    const path = input.trim().replace(/^\/+/, "");
    setDraft({ path: /\.md$/i.test(path) ? path : `${path}.md`, body: "", exists: false });
    setNotice(null);
  };

  const groups = useMemo(() => groupByFolder(pages), [pages]);
  const source = useMemo(() => (page ? wikilinksToMarkdown(page.body) : ""), [page]);

  return (
    <div className="layout">
      <nav className="sidebar" aria-label="Seiten">
        <a className="brand" href="#/">
          Wiki
        </a>
        <input
          className="search"
          type="search"
          placeholder="Suchen…"
          aria-label="Suchen"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <a className="graphlink" href="#/graph" aria-current={showGraph ? "page" : undefined}>
          Graph
        </a>
        {editable && (
          <button type="button" className="newpage" onClick={newPage}>
            + Neue Seite
          </button>
        )}
        {query.trim().length >= 2 ? (
          <ul className="hits">
            {hits.length === 0 && <li className="muted">Keine Treffer</li>}
            {hits.map((h) => (
              <li key={h.path}>
                <a href={pageHref(h.path)} onClick={() => setQuery("")}>
                  {h.title}
                </a>
                {h.snippet && <small>{h.snippet}</small>}
              </li>
            ))}
          </ul>
        ) : (
          groups.map(([folder, items]) => (
          <section key={folder}>
            {folder && <h2>{folder}</h2>}
            <ul>
              {items.map((p) => (
                <li key={p.path}>
                  <a href={pageHref(p.path)} aria-current={p.path === current ? "page" : undefined}>
                    {p.title}
                  </a>
                </li>
              ))}
            </ul>
          </section>
          ))
        )}
      </nav>
      <main className="content">
        {notice && (
          <p className={notice.kind === "ok" ? "notice" : "error"} role="status">
            {notice.text}{" "}
            {notice.url && (
              <a href={notice.url} target="_blank" rel="noreferrer">
                {notice.url}
              </a>
            )}
          </p>
        )}
        {showGraph && <GraphView current={lastViewed} />}
        {!showGraph && draft && (
          <article>
            <h1 className="draft-path">{draft.path}</h1>
            <Editor
              key={draft.path}
              initialBody={draft.body}
              busy={busy}
              onDirty={() => {
                dirty.current = true;
              }}
              onSave={save}
              onCancel={() => setDraft(null)}
            />
          </article>
        )}
        {!showGraph && !draft && error && <p className="error">{error}</p>}
        {!showGraph && !draft && page && (
          <article>
            {editable && (
              <div className="actions top">
                <button
                  type="button"
                  onClick={() => setDraft({ path: page.path, body: page.body, exists: true })}
                >
                  Bearbeiten
                </button>
                {page.path !== "index.md" && (
                  <button type="button" onClick={remove}>
                    Löschen
                  </button>
                )}
              </div>
            )}
            {page.tags.length > 0 && (
              <div className="tags">
                {page.tags.map((t) => (
                  <span key={t} className="tag">
                    {t}
                  </span>
                ))}
              </div>
            )}
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeSanitize]}
              components={{
                a({ href = "", children }) {
                  if (href.startsWith("#wl=")) {
                    const target = resolveWikilink(href.slice(4), pages);
                    return target ? (
                      <a href={pageHref(target)}>{children}</a>
                    ) : (
                      <span className="missing" title="Seite existiert nicht">
                        {children}
                      </span>
                    );
                  }
                  const rel = resolveRelative(href, page.path);
                  if (rel) return <a href={pageHref(rel)}>{children}</a>;
                  const external = /^https?:/i.test(href);
                  return (
                    <a href={href} {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
                      {children}
                    </a>
                  );
                },
              }}
            >
              {source}
            </ReactMarkdown>
            {page.backlinks.length > 0 && (
              <aside className="backlinks">
                <h2>Verlinkt von</h2>
                <ul>
                  {page.backlinks.map((b) => (
                    <li key={b}>
                      <a href={pageHref(b)}>{pages.find((p) => p.path === b)?.title ?? b}</a>
                    </li>
                  ))}
                </ul>
              </aside>
            )}
          </article>
        )}
      </main>
    </div>
  );
}
