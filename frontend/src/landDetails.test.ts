import { describe, expect, it } from "vitest";
import {
  EMPTY_LAND_DETAILS,
  TEMPERATURE_MAX_C,
  TEMPERATURE_MIN_C,
  clearLandField,
  isValidTemperatureC,
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

  it("sends pesticide_use without mapping it to pollution", () => {
    const payload = toStructuredPayload({
      ...EMPTY_LAND_DETAILS,
      pesticide_use: "none",
      crop: "wheat",
    });
    expect(payload).toEqual({ crop: "wheat", pesticide_use: "none" });
    expect(payload).not.toHaveProperty("pollution");
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

  it("accepts environmental temperatures up to 80°C", () => {
    expect(TEMPERATURE_MIN_C).toBe(-40);
    expect(TEMPERATURE_MAX_C).toBe(80);
    expect(isValidTemperatureC(60)).toBe(true);
    expect(isValidTemperatureC(65)).toBe(true);
    expect(isValidTemperatureC(80)).toBe(true);
    expect(isValidTemperatureC(80.1)).toBe(false);
    expect(toStructuredPayload({ ...EMPTY_LAND_DETAILS, temperature: "65" }).temperature).toBe(65);
    expect(toStructuredPayload({ ...EMPTY_LAND_DETAILS, temperature: "60" }).temperature).toBe(60);
    expect(toStructuredPayload({ ...EMPTY_LAND_DETAILS, temperature: "80" }).temperature).toBe(80);
    expect(mergeStructuredSources({ ...EMPTY_LAND_DETAILS, temperature: "65" }, "")).toMatchObject({
      temperature: 65,
    });
    expect(mergeStructuredSources({ ...EMPTY_LAND_DETAILS, temperature: "80" }, "")).toMatchObject({
      temperature: 80,
    });
    expect(() => mergeStructuredSources({ ...EMPTY_LAND_DETAILS, temperature: "81" }, "")).toThrow(
      /80/,
    );
  });
});
