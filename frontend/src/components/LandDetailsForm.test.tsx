import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EMPTY_LAND_DETAILS, LandDetails } from "../landDetails";
import { LandDetailsForm } from "./LandDetailsForm";

vi.mock("../api", () => ({
  searchLocations: vi.fn(async () => [
    { label: "Pune, Maharashtra, India", latitude: 18.5204, longitude: 73.8567 },
  ]),
}));

vi.mock("./LocationPicker", () => ({
  LocationPicker: ({ onSelect }: { onSelect: (lat: number, lng: number) => void }) => (
    <button type="button" onClick={() => onSelect(18.5204, 73.8567)}>
      Pick map point
    </button>
  ),
}));

function Harness({ onClose = () => undefined }: { onClose?: () => void }) {
  const [details, setDetails] = useState<LandDetails>(EMPTY_LAND_DETAILS);
  return (
    <div>
      <LandDetailsForm details={details} onChange={setDetails} onClose={onClose} />
      <pre data-testid="payload">{JSON.stringify(details)}</pre>
    </div>
  );
}

describe("LandDetailsForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps every field optional", () => {
    render(<Harness />);
    expect(screen.getByPlaceholderText("e.g. 10 acres")).toHaveValue("");
    expect(screen.getByPlaceholderText("e.g. wheat")).toHaveValue("");
    fireEvent.change(screen.getByPlaceholderText("e.g. wheat"), { target: { value: "wheat" } });
    expect(screen.getByTestId("payload").textContent).toContain("wheat");
    expect(JSON.parse(screen.getByTestId("payload").textContent || "{}").soil_ph).toBe("");
  });

  it("stores coordinates from a map selection", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Pick map point"));
    const stored = JSON.parse(screen.getByTestId("payload").textContent || "{}");
    expect(stored.latitude).toBe("18.5204");
    expect(stored.longitude).toBe("73.8567");
  });

  it("lets the user type a location in one go", () => {
    render(<Harness />);
    const input = screen.getByPlaceholderText("Search a place or type a location");
    fireEvent.change(screen.getByPlaceholderText("e.g. wheat"), { target: { value: "wheat" } });
    fireEvent.change(input, { target: { value: "s" } });
    fireEvent.change(input, { target: { value: "sh" } });
    fireEvent.change(input, { target: { value: "shah" } });
    expect(input).toHaveValue("shah");
    fireEvent.blur(input);
    expect(JSON.parse(screen.getByTestId("payload").textContent || "{}").location).toBe("shah");
  });

  it("stores coordinates from a location search result", async () => {
    render(<Harness />);
    fireEvent.change(screen.getByPlaceholderText("Search a place or type a location"), {
      target: { value: "Pune" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("button", { name: "Pune, Maharashtra, India" })).toBeInTheDocument();
    await waitFor(() => {
      const stored = JSON.parse(screen.getByTestId("payload").textContent || "{}");
      expect(stored.latitude).toBe("18.5204");
      expect(stored.longitude).toBe("73.8567");
    });
    fireEvent.click(screen.getByRole("button", { name: "Pune, Maharashtra, India" }));
    const stored = JSON.parse(screen.getByTestId("payload").textContent || "{}");
    expect(stored.location).toContain("Pune");
    expect(stored.latitude).toBe("18.5204");
    expect(stored.longitude).toBe("73.8567");
  });

  it("opens a large map and returns to the compact view", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "View large map" }));
    expect(screen.getByTestId("land-map-stage")).toHaveClass("expanded");
    expect(screen.getByRole("button", { name: "Close large map" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByTestId("land-map-stage")).not.toHaveClass("expanded");
    fireEvent.click(screen.getByRole("button", { name: "View large map" }));
    fireEvent.click(screen.getByRole("button", { name: "Close large map" }));
    expect(screen.getByTestId("land-map-stage")).not.toHaveClass("expanded");
  });

  it("accepts temperatures above 60°C within the 80°C environmental limit", () => {
    render(<Harness />);
    const input = screen.getByPlaceholderText("°C");
    expect(input).toHaveAttribute("min", "-40");
    expect(input).toHaveAttribute("max", "80");
    fireEvent.change(input, { target: { value: "65" } });
    expect(JSON.parse(screen.getByTestId("payload").textContent || "{}").temperature).toBe("65");
  });

  it("closes when requested", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Add land details" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
