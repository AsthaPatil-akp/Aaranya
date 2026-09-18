import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatResponse, postChatStream } from "../api";
import { downloadActionPlanPdf } from "../actionPlanPdf";
import { Lab } from "./Lab";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    postChatStream: vi.fn(),
    searchLocations: vi.fn(async () => []),
  };
});

vi.mock("../actionPlanPdf", () => ({
  downloadActionPlanPdf: vi.fn(),
}));

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
    vi.mocked(downloadActionPlanPdf).mockReset();
  });

  it("opens and closes the optional land details dialog", () => {
    render(<Lab />);
    const addLand = screen.getByTestId("add-land-details");
    expect(addLand).toHaveClass("inverse");
    expect(screen.queryByRole("dialog", { name: "Add land details" })).not.toBeInTheDocument();
    fireEvent.click(addLand);
    expect(screen.getByRole("dialog", { name: "Add land details" })).toBeInTheDocument();
    expect(screen.getByTestId("land-details-form")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Add land details" })).not.toBeInTheDocument();
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

  it("renders impacted metrics returned by the backend", async () => {
    vi.mocked(postChatStream).mockResolvedValue({
      ...emptyResponse,
      mode: "recommendation",
      assistant_message: "Keep residue and add cover crops.",
      knowledge_status: "grounded_in_knowledge_base",
      knowledge_status_label: "Grounded in knowledge base",
      kb_evidence: [
        {
          source: "01.md",
          document_name: "01.md",
          title: "Unused retrieved title",
          page: null,
          topic: null,
          document_type: null,
          passage: "Unused.",
          relevance_score: 0.1,
          origin: "knowledge_base",
        },
      ],
      recommendation: {
        action: "Keep residue and add drought-tolerant cover crops.",
        why_it_works: "Retrieved passages link residue to soil function.",
        environmental_relationships: "Soil carbon and moisture may interact.",
        impacted_metrics: [
          { name: "Soil organic carbon", direction: "unknown", note: "potentially affected" },
          { name: "Pollinator diversity", direction: "unknown", note: "possible local improvement" },
        ],
        time_horizon: {
          narrative: "No specific timeframe is supported by the retrieved evidence.",
          evidence_supported: false,
        },
        uncertainty: "Local trials are still needed.",
        confidence: "medium",
        confidence_rationale: "Retrieved passages were available.",
        items: [
          {
            action: "Keep residue and add drought-tolerant cover crops.",
            why: "Retrieved passages link residue to soil function.",
            impacted_metrics: [
              { name: "Soil organic carbon", direction: "unknown", note: "potentially affected" },
            ],
            time_horizon: "No specific timeframe is supported by the retrieved evidence.",
            supporting_evidence: ["Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity"],
          },
          {
            action: "kb-76: Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity",
            why: "Should not appear as a recommendation.",
            impacted_metrics: [],
            time_horizon: "",
            supporting_evidence: [],
          },
        ],
        supporting_evidence: ["Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity"],
      },
    });
    render(<Lab />);
    fireEvent.change(screen.getByPlaceholderText(/Type a new question/), {
      target: { value: "What should I do on my wheat farm?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByTestId("recommendation-panel")).toBeInTheDocument();
    const panel = screen.getByTestId("recommendation-panel");
    expect(within(panel).getByText(/Keep residue and add drought-tolerant cover crops/)).toBeInTheDocument();
    expect(within(panel).getByText(/Retrieved passages link residue to soil function/)).toBeInTheDocument();
    expect(within(panel).getByText(/Soil organic carbon/)).toBeInTheDocument();
    expect(within(panel).getByText(/potentially affected/)).toBeInTheDocument();
    expect(within(panel).getByText(/No specific timeframe is supported by the retrieved evidence/)).toBeInTheDocument();
    expect(within(panel).getByText(/Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity/)).toBeInTheDocument();
    expect(within(panel).queryByText("Unused retrieved title")).not.toBeInTheDocument();
    expect(within(panel).queryByText(/Duplicate should be hidden/)).not.toBeInTheDocument();
    expect(within(panel).queryByText(/kb-76/)).not.toBeInTheDocument();
    expect(within(panel).getByText(/Why:/)).toBeInTheDocument();
    expect(within(panel).getByText(/Supporting evidence/)).toBeInTheDocument();
  });

  it("maps parent recommendation fields when item details are empty", async () => {
    vi.mocked(postChatStream).mockResolvedValue({
      ...emptyResponse,
      mode: "recommendation",
      assistant_message: "Cover crops may help in this dry wheat field.",
      knowledge_status: "grounded_in_knowledge_base",
      knowledge_status_label: "Grounded in knowledge base",
      recommendation: {
        action: "Use drought-tolerant cover crops in the fallow window.",
        why_it_works: "Low soil carbon and low rainfall interact.",
        environmental_relationships: "Organic carbon and rainfall act together.",
        impacted_metrics: [
          { name: "Soil organic carbon", direction: "unknown", note: "potentially affected" },
        ],
        time_horizon: {
          narrative: "Several seasons to multiple years",
          evidence_supported: true,
        },
        uncertainty: null,
        confidence: "medium",
        confidence_rationale: "Retrieved passages were available.",
        items: [
          {
            action: "Use drought-tolerant cover crops in the fallow window.",
            why: "",
            impacted_metrics: [],
            time_horizon: "",
            supporting_evidence: [],
          },
        ],
        supporting_evidence: ["Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming"],
      },
    });
    render(<Lab />);
    fireEvent.click(screen.getByRole("button", { name: "Demo: farm profile" }));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByTestId("recommendation-panel")).toBeInTheDocument();
    expect(screen.getByText(/Low soil carbon and low rainfall interact/)).toBeInTheDocument();
    expect(screen.getByText(/Soil organic carbon/)).toBeInTheDocument();
    expect(screen.getByText(/Several seasons to multiple years/)).toBeInTheDocument();
    expect(
      screen.getByText(/Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming/),
    ).toBeInTheDocument();
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
      debug: false,
    });
    expect(payload.structured).toBeUndefined();
  });

  it("renders assistant markdown tables instead of pipe syntax", async () => {
    vi.mocked(postChatStream).mockResolvedValue({
      ...emptyResponse,
      mode: "recommendation",
      assistant_message:
        "## Assessment Summary\nLow carbon and rainfall can interact.\n\n## Recommendations\n| Action | Why it may help |\n| --- | --- |\n| Keep residue | Supports soil cover |\n",
    });
    render(<Lab />);
    fireEvent.change(screen.getByPlaceholderText(/Type a new question/), {
      target: { value: "What should I do on my wheat farm?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByTestId("assistant-markdown")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Action" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Keep residue" })).toBeInTheDocument();
    expect(screen.queryByText(/\| Action \|/)).not.toBeInTheDocument();
  });

  it("copies an assistant answer", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<Lab />);
    fireEvent.change(screen.getByPlaceholderText(/Type a new question/), {
      target: { value: "Biodiversity is declining on my farm." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("button", { name: "Copy answer" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(emptyResponse.assistant_message));
    expect(screen.getByRole("button", { name: "Answer copied" })).toBeInTheDocument();
  });

  it("offers an action plan PDF beside a completed response", async () => {
    render(<Lab />);
    fireEvent.change(screen.getByPlaceholderText(/Type a new question/), {
      target: { value: "Biodiversity is declining on my farm." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const button = await screen.findByRole("button", { name: "Download Action Plan PDF" });
    fireEvent.click(button);
    expect(downloadActionPlanPdf).toHaveBeenCalledWith(emptyResponse, expect.any(Object));
  });
});
