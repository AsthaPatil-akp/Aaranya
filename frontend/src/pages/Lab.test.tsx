import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatResponse, postChatStream } from "../api";
import { Lab } from "./Lab";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    postChatStream: vi.fn(),
    searchLocations: vi.fn(async () => []),
  };
});

vi.mock("../components/LocationPicker", () => ({
  LocationPicker: ({ onSelect }: { onSelect: (lat: number, lng: number) => void }) => (
    <button type="button" onClick={() => onSelect(12.97, 77.59)}>
      Pick map point
    </button>
  ),
}));

const emptyResponse: ChatResponse = {
  session_id: "session-1",
  mode: "clarification",
  assistant_message: "Could you share soil carbon or rainfall?",
  clarifying_questions: ["What is the soil organic carbon level (percent or low/moderate/high)?"],
  environmental_context: {},
  known_variables: {},
  profile: null,
  recommendation: null,
  evidence: [],
  kb_evidence: [],
  external_evidence: [],
  knowledge_status: "awaiting_clarification",
  knowledge_status_label: "Waiting for a clearer site picture",
  debug: null,
  warnings: [],
};

describe("Intelligence Lab land details", () => {
  beforeEach(() => {
    vi.mocked(postChatStream).mockReset();
    vi.mocked(postChatStream).mockResolvedValue(emptyResponse);
  });

  it("opens and closes the optional land details form", () => {
    render(<Lab />);
    expect(screen.queryByTestId("land-details-form")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("add-land-details"));
    expect(screen.getByTestId("land-details-form")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByTestId("land-details-form")).not.toBeInTheDocument();
  });

  it("sends structured land details with the chat message", async () => {
    render(<Lab />);
    fireEvent.click(screen.getByTestId("add-land-details"));
    fireEvent.change(screen.getByPlaceholderText("e.g. 10 acres"), { target: { value: "5 acres" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. wheat"), { target: { value: "wheat" } });
    fireEvent.click(screen.getByText("Pick map point"));
    fireEvent.change(screen.getByPlaceholderText(/Type a new question/), {
      target: { value: "Biodiversity is declining on my farm." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(postChatStream).toHaveBeenCalled());
    const payload = vi.mocked(postChatStream).mock.calls[0][0];
    expect(payload.message).toBe("Biodiversity is declining on my farm.");
    expect(payload.structured).toMatchObject({
      farm_size: "5 acres",
      crop: "wheat",
      latitude: 12.97,
      longitude: 77.59,
    });
    expect(payload.structured).not.toHaveProperty("soil_ph");
    expect(payload.structured).not.toHaveProperty("rainfall");
    expect(screen.getByTestId("land-detail-chips")).toBeInTheDocument();
  });

  it("keeps existing chat send behaviour when the form is unused", async () => {
    render(<Lab />);
    expect(screen.getByRole("button", { name: "Demo: incomplete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Demo: farm profile" })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Type a new question/), {
      target: { value: "Biodiversity is declining on my farm." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(postChatStream).toHaveBeenCalled());
    const payload = vi.mocked(postChatStream).mock.calls[0][0];
    expect(payload).toMatchObject({
      message: "Biodiversity is declining on my farm.",
      debug: true,
    });
    expect(payload.structured).toBeUndefined();
  });
});
