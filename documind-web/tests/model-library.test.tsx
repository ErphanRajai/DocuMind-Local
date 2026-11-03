import { it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ModelLibrary } from "../components/model-library";
import { api } from "../lib/api";
vi.mock("../lib/api", () => ({
  api: vi.fn(),
  post: (value: unknown) => ({ method: "POST", body: JSON.stringify(value) }),
}));
const old = "llama3.2:3b",
  fresh = "qwen3:4b-instruct-2507-q4_K_M";
const preview = {
  id: "p",
  model: fresh,
  directory: "D:\\Models",
  model_bytes: 3 * 1024 ** 3,
  download_bytes: 3 * 1024 ** 3,
  free_bytes: 20 * 1024 ** 3,
  copy_bytes: 0,
  restart_required: false,
};
const catalogue = {
  models: [
    { name: old, installed: true, description: "Existing model" },
    { name: fresh, installed: false, description: "Multilingual" },
  ],
  directory: preview.directory,
  windows_console: true,
  ollama_available: true,
  download_available: true,
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api).mockImplementation(async (path) =>
    path.endsWith("catalog")
      ? catalogue
      : path.endsWith("preview")
        ? preview
        : {
            ...preview,
            id: "a".repeat(32),
            state: "queued",
            message: "Opening Command Prompt",
            total: 0,
            completed: 0,
          },
  );
});
const props = {
  model: old,
  installed: [old],
  onSelect: vi.fn(),
  onInstalled: vi.fn(),
};
it("labels missing models and previews size without changing the answer model or downloading", async () => {
  render(<ModelLibrary {...props} />);
  await screen.findByText(`${fresh} — Not installed`);
  fireEvent.change(screen.getByLabelText("Model library"), {
    target: { value: fresh },
  });
  await screen.findByRole("region", { name: "Review model installation" });
  expect(screen.getAllByText("3.00 GiB")).toHaveLength(2);
  expect(props.onSelect).not.toHaveBeenCalled();
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path.endsWith("/install")),
  ).toBe(false);
  fireEvent.click(screen.getByText("Install in Command Prompt"));
  await screen.findByText("Opening Command Prompt");
  const call = vi
    .mocked(api)
    .mock.calls.find(([path]) => path.endsWith("/install"));
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ preview_id: "p" });
});
it("invalidates the size/folder confirmation when the destination changes", async () => {
  render(<ModelLibrary {...props} />);
  await screen.findByLabelText("Model library folder");
  fireEvent.click(screen.getByText("Review download size & folder"));
  await screen.findByText("Install in Command Prompt");
  fireEvent.change(screen.getByLabelText("Model library folder"), {
    target: { value: "E:\\NewModels" },
  });
  expect(screen.queryByText("Install in Command Prompt")).toBeNull();
});
it("shows launcher-unavailable errors while preserving installed-model selection", async () => {
  vi.mocked(api).mockRejectedValue(new Error("Open Start_DocuMind.bat"));
  render(<ModelLibrary {...props} installed={[old, fresh]} />);
  await screen.findByText("Open Start_DocuMind.bat");
  fireEvent.change(screen.getByLabelText("Model library"), {
    target: { value: fresh },
  });
  expect(props.onSelect).toHaveBeenCalledWith(fresh);
  expect(screen.queryByText("Install in Command Prompt")).toBeNull();
});
it("keeps installation failure retryable and displays the destination restart requirement", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith("catalog")) return catalogue;
    if (path.endsWith("preview"))
      return { ...preview, restart_required: true, copy_bytes: 2 * 1024 ** 3 };
    throw new Error("Command Prompt could not open");
  });
  render(<ModelLibrary {...props} />);
  await screen.findByLabelText("Model library folder");
  fireEvent.click(screen.getByText("Review download size & folder"));
  await screen.findByText("Existing library copy");
  expect(
    screen.getByText(/Restart DocuMind after installation/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByText("Install in Command Prompt"));
  await screen.findByRole("alert");
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Command Prompt could not open",
  );
  await waitFor(() =>
    expect(screen.getByText("Review download size & folder")).toBeEnabled(),
  );
});
