import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

vi.mock("./Editor", () => ({
  Editor: ({ onDirty }: { onDirty?: () => void }) => (
    <button type="button" onClick={onDirty}>
      tippen
    </button>
  ),
}));

const pages = [
  { path: "index.md", title: "Willkommen", tags: [] },
  { path: "b.md", title: "Zweite", tags: [] },
];

function stubApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () => {
          if (url === "/api/config") return { editable: true };
          if (url === "/api/pages") return pages;
          return { ...pages[0], body: "# Hallo", backlinks: [] };
        },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

async function openDirtyEditor() {
  stubApi();
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
  fireEvent.click(await screen.findByRole("button", { name: "tippen" }));
}

test("keeps the draft when the user declines to leave", async () => {
  await openDirtyEditor();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  window.location.hash = "#/b.md";
  await vi.waitFor(() => expect(confirm).toHaveBeenCalled());
  await vi.waitFor(() => expect(window.location.hash).toBe(""));
  expect(screen.getByRole("button", { name: "tippen" })).toBeTruthy();
});

test("discards the draft when the user confirms", async () => {
  await openDirtyEditor();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  window.location.hash = "#/b.md";
  await vi.waitFor(() => expect(screen.queryByRole("button", { name: "tippen" })).toBeNull());
});

test("a clean draft is left without asking", async () => {
  stubApi();
  const confirm = vi.spyOn(window, "confirm");
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
  window.location.hash = "#/b.md";
  await vi.waitFor(() => expect(screen.queryByRole("button", { name: "tippen" })).toBeNull());
  expect(confirm).not.toHaveBeenCalled();
});
