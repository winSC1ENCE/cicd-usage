import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

afterEach(() => vi.unstubAllGlobals());

test("shows navigation and renders the start page with a wikilink", async () => {
  const pages = [
    { path: "index.md", title: "Willkommen", tags: ["demo"] },
    { path: "HowTo/Beispiel.md", title: "Beispiel", tags: [] },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url === "/api/pages"
            ? pages
            : {
                ...pages[0],
                body: "# Hallo\n\nSiehe [[Beispiel]]",
                backlinks: ["HowTo/Beispiel.md"],
              },
      }),
    ),
  );
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Hallo" })).toBeTruthy();
  const link = screen.getAllByRole("link", { name: "Beispiel" }).pop()!;
  expect(link.getAttribute("href")).toBe("#/HowTo/Beispiel.md");
  expect(screen.getByText("Verlinkt von")).toBeTruthy();
});

test("edit button opens the editor and saving sends a PUT", async () => {
  const pages = [{ path: "index.md", title: "Willkommen", tags: [] }];
  localStorage.setItem("wiki-author", "Nico");
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) =>
    Promise.resolve({
      ok: true,
      json: async () => {
        if (url === "/api/config") return { editable: true };
        if (url === "/api/pages") return pages;
        if (init?.method === "PUT") return { merge_request: "https://gitlab.example/mr/1" };
        return { ...pages[0], body: "# Hallo", backlinks: [] };
      },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
  fireEvent.click(await screen.findByRole("button", { name: "Als Merge Request speichern" }));
  expect(await screen.findByText("https://gitlab.example/mr/1")).toBeTruthy();
  const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(JSON.parse(put[1]!.body!)).toMatchObject({ author: "Nico" });
});
