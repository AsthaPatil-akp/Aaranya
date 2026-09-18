import { describe, expect, it } from "vitest";
import {
  EMPTY_LAND_DETAILS,
  clearLandField,
  landDetailChips,
  mergeStructuredSources,
  toStructuredPayload,
} from "./landDetails";

describe("optional land details payload", () => {
  it("omits empty fields", () => {
    expect(toStructuredPayload(EMPTY_LAND_DETAILS)).toEqual({});
    expect(
      toStructuredPayload({
        ...EMPTY_LAND_DETAILS,
        crop: "wheat",
        farm_size: "  ",
      }),
    ).toEqual({ crop: "wheat" });
  });

  it("stores numeric coordinates when a map point is selected", () => {
    const payload = toStructuredPayload({
      ...EMPTY_LAND_DETAILS,
      latitude: "18.5204",
      longitude: "73.8567",
    });
    expect(payload.latitude).toBe(18.5204);
    expect(payload.longitude).toBe(73.8567);
    const chips = landDetailChips({
      ...EMPTY_LAND_DETAILS,
      latitude: "18.5204",
      longitude: "73.8567",
    });
    expect(chips.some((chip) => chip.label === "Map point")).toBe(true);
  });

  it("clears map coordinates together", () => {
    const next = clearLandField(
      { ...EMPTY_LAND_DETAILS, latitude: "18.5", longitude: "73.8", crop: "wheat" },
      "latitude",
    );
    expect(next.latitude).toBe("");
    expect(next.longitude).toBe("");
    expect(next.crop).toBe("wheat");
  });

  it("merges form details over optional JSON", () => {
    const combined = mergeStructuredSources(
      { ...EMPTY_LAND_DETAILS, crop: "wheat", latitude: "12.9", longitude: "77.6" },
      '{"crop":"maize","rainfall":"low"}',
    );
    expect(combined).toMatchObject({
      crop: "wheat",
      rainfall: "low",
      latitude: 12.9,
      longitude: 77.6,
    });
  });
});
