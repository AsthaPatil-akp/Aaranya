import { describe, expect, it } from "vitest";
import { buildActionPlan, planSections } from "./actionPlan";
import { extractPdfCharSpaces, extractPdfText, extractPdfWordSpaces, renderActionPlanPdf } from "./actionPlanPdf";
import { ChatResponse } from "./api";
import { PDF_HEADING } from "./brand";
import { EMPTY_LAND_DETAILS, LandDetails } from "./landDetails";

const baseResponse: ChatResponse = {
  session_id: "session-1",
  mode: "clarification",
  assistant_message: "Could you share soil carbon or rainfall?",
  clarifying_questions: [],
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

describe("action plan PDF data", () => {
  it("omits missing land details and does not invent values", () => {
    const plan = buildActionPlan(baseResponse, EMPTY_LAND_DETAILS);
    expect(plan.heading).toBe(PDF_HEADING);
    expect(plan.siteProfile).toEqual([]);
    expect(plan.recommendations).toEqual([]);
    expect(plan.monitoring).toEqual([]);
    expect(plan.kbSources).toEqual([]);
    expect(plan.externalSources).toEqual([]);
    expect(plan.assessment).toContain("soil carbon");
    expect(JSON.stringify(plan)).not.toContain("25%");
    expect(JSON.stringify(plan)).not.toContain("10-20 years");
  });

  it("uses provided land details, grounded recommendations, and only used sources", () => {
    const details: LandDetails = {
      ...EMPTY_LAND_DETAILS,
      farm_size: "5 acres",
      location: "semi-arid district",
      latitude: "12.97",
      longitude: "77.59",
      crop: "wheat",
      land_use: "monoculture",
      soil_organic_carbon: "0.3",
    };
    const response: ChatResponse = {
      ...baseResponse,
      mode: "recommendation",
      assistant_message:
        "Low soil carbon and low rainfall can interact. Cover crops may help.\n\nSources / Evidence\n- Cover Crops",
      known_variables: {
        crop: "wheat",
        soil_organic_carbon: 0.3,
        rainfall: "low",
      },
      knowledge_status: "grounded_in_knowledge_base",
      knowledge_status_label: "Grounded in knowledge base",
      recommendation: {
        action: "Keep residue and add drought-tolerant cover crops.",
        why_it_works: "Retrieved passages link residue to soil function.",
        environmental_relationships: "Soil carbon and rainfall may interact.",
        impacted_metrics: [
          { name: "Soil organic carbon", direction: "unknown", note: "potentially affected" },
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
            supporting_evidence: ["Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming"],
          },
        ],
        supporting_evidence: ["Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming"],
      },
      kb_evidence: [
        {
          source: "04.md",
          document_name: "04.md",
          title: "Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
          page: null,
          topic: null,
          document_type: null,
          passage: "Cover crops and residue can support water holding.",
          relevance_score: 0.8,
          origin: "knowledge_base",
          url: null,
          doi: null,
        },
      ],
      external_evidence: [],
    };
    const plan = buildActionPlan(response, details);
    expect(plan.siteProfile.map((row) => row.label)).toEqual(
      expect.arrayContaining(["Location", "Map coordinates", "Farm size", "Crop / vegetation", "Land use"]),
    );
    expect(plan.siteProfile.find((row) => row.label === "Pollution")).toBeUndefined();
    expect(plan.assessment).toContain("Cover crops may help");
    expect(plan.assessment).not.toContain("Sources / Evidence");
    expect(plan.assessment).not.toMatch(/\|/);
    expect(plan.recommendations).toHaveLength(1);
    expect(plan.recommendations[0].why).toContain("residue");
    expect(plan.monitoring).toEqual([
      { metric: "Soil organic carbon", frequency: "" },
    ]);
    expect(plan.kbSources).toHaveLength(1);
    expect(plan.externalSources).toEqual([]);
    expect(plan.limitations.join(" ")).toContain("Local trials are still needed");
  });

  it("fills monitoring frequency only when the timeframe is evidence-supported", () => {
    const response: ChatResponse = {
      ...baseResponse,
      mode: "recommendation",
      assistant_message: "Cover can appear over several seasons.",
      recommendation: {
        action: "Keep residue.",
        why_it_works: "Residue can protect soil.",
        environmental_relationships: "",
        impacted_metrics: [{ name: "Soil moisture", direction: "unknown", note: "potentially affected" }],
        time_horizon: {
          narrative: "Several seasons to multiple years",
          evidence_supported: true,
        },
        confidence: "low",
        confidence_rationale: "Limited retrieved evidence.",
      },
    };
    const plan = buildActionPlan(response, EMPTY_LAND_DETAILS);
    expect(plan.monitoring[0]).toEqual({
      metric: "Soil moisture",
      frequency: "Several seasons to multiple years",
    });
  });

  it("renders a PDF for sparse and complete plans", async () => {
    const sparse = await renderActionPlanPdf(buildActionPlan(baseResponse, EMPTY_LAND_DETAILS));
    expect(sparse.bytes.byteLength).toBeGreaterThan(500);
    const complete = await renderActionPlanPdf(
      buildActionPlan(
        {
          ...baseResponse,
          mode: "recommendation",
          assistant_message: "Cover crops may help in this dry wheat field.",
          known_variables: { crop: "wheat" },
          recommendation: {
            action: "Keep residue.",
            why_it_works: "Residue can protect soil.",
            environmental_relationships: "",
            impacted_metrics: [{ name: "Soil organic carbon", direction: "unknown", note: "potentially affected" }],
            time_horizon: { narrative: "Several seasons to multiple years", evidence_supported: true },
            uncertainty: "Outcomes still depend on rainfall.",
            confidence: "medium",
            confidence_rationale: "Retrieved passages were available.",
          },
          kb_evidence: [
            {
              source: "01.md",
              document_name: "01.md",
              title: "Soil Organic Carbon",
              page: null,
              topic: null,
              document_type: null,
              passage: "Cover crops can add residue.",
              relevance_score: 0.7,
              origin: "knowledge_base",
            },
          ],
        },
        { ...EMPTY_LAND_DETAILS, crop: "wheat", farm_size: "5 acres" },
      ),
    );
    expect(complete.pageCount).toBeGreaterThanOrEqual(1);
    expect(complete.bytes.byteLength).toBeGreaterThan(sparse.bytes.byteLength);
  });

  it("renders recommendation markdown as a PDF table without pipe syntax", async () => {
    const doc = await renderActionPlanPdf(
      buildActionPlan(
        {
          ...baseResponse,
          mode: "recommendation",
          assistant_message: [
            "## Assessment Summary",
            "Low soil carbon and low rainfall can interact.",
            "",
            "## Recommendations",
            "| Action | Why it may help | Supporting evidence |",
            "| --- | --- | --- |",
            "| Keep residue | Supports soil cover | Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming |",
            "",
            "## Recommendations",
            "| Action | Why it may help | Supporting evidence |",
            "| --- | --- | --- |",
            "| Keep residue | Supports soil cover | Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming |",
            "",
            "## Sources / Evidence",
            "- kb-14",
          ].join("\n"),
          recommendation: {
            action: "Keep residue.",
            why_it_works: "Residue can protect soil.",
            environmental_relationships: "",
            impacted_metrics: [{ name: "Soil organic carbon", direction: "unknown", note: "potentially affected" }],
            time_horizon: { narrative: "Several seasons to multiple years", evidence_supported: true },
            uncertainty: "Outcomes still depend on rainfall.",
            confidence: "medium",
            confidence_rationale: "Retrieved passages were available.",
          },
          kb_evidence: [
            {
              source: "02.md",
              document_name: "02.md",
              title: "Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
              page: null,
              topic: null,
              document_type: null,
              passage: "Cover crops and residue can support water holding.",
              relevance_score: 0.8,
              origin: "knowledge_base",
            },
          ],
        },
        EMPTY_LAND_DETAILS,
      ),
    );
    const text = extractPdfText(doc);
    expect(text).not.toMatch(/\|\s*Action\s*\|/);
    expect(text).not.toMatch(/kb-14/);
    expect(text).toContain("Keep residue");
  });

  it("renders a full action-plan sample without raw markdown or letter-spacing", async () => {
    const assistantMessage = `## Assessment Summary

Your 5 acre wheat field in a semi-arid region has low soil organic carbon and low soil moisture. Drought-tolerant cover is a better fit than dense planting.

## What to investigate first

1. **Measure SOC** - Determine whether SOC is low, moderate, or high. A quick test will confirm whether carbon levels are low and how quickly the soil dries.

2. **Map current intercropping patterns.** Identify companion species, drought tolerance, and flowering strips.

3. **Assess residue retention.** Determine how much crop residue remains after harvest.

## Recommendations

| Intervention | What to do | Why it may help | Metrics |
|---|---|---|---|
| Cover crops | Plant a drought-tolerant cover crop | Adds organic matter and living roots | SOC, soil moisture |
| Agroforestry | Add widely spaced trees/shrubs | Provides habitat and wind protection | SOC, habitat |
| Flowering strips | Add flowering plants | Provides pollinator resources | Pollinator activity |

## Why these work together

Cover, trees and flowers address soil carbon, habitat and pollinators together rather than as isolated fixes.

## Next steps

1. Start with a small cover-crop strip.
2. Keep residue on the soil surface.
3. Review results after a season.

## Sources / Evidence

- Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming

## Uncertainty

Local trials are still needed before promising a specific yield or species response.
`;
    const doc = await renderActionPlanPdf(
      buildActionPlan(
        {
          ...baseResponse,
          mode: "recommendation",
          assistant_message: assistantMessage,
          known_variables: { crop: "wheat", farm_size: "5 acres" },
          recommendation: {
            action: "Plant a drought-tolerant cover crop.",
            why_it_works: "Adds organic matter and living roots.",
            environmental_relationships: "Cover, trees and flowers address soil carbon together.",
            impacted_metrics: [{ name: "Soil organic carbon", direction: "unknown", note: "potentially affected" }],
            time_horizon: { narrative: "Several seasons to multiple years", evidence_supported: true },
            uncertainty: "Local trials are still needed before promising a specific yield or species response.",
            confidence: "medium",
            confidence_rationale: "Retrieved passages were available.",
            items: [
              {
                action: "Plant a drought-tolerant cover crop.",
                why: "Adds organic matter and living roots.",
                impacted_metrics: [{ name: "Soil organic carbon", direction: "unknown", note: "potentially affected" }],
                time_horizon: "Several seasons to multiple years",
                supporting_evidence: ["Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming"],
              },
            ],
          },
          kb_evidence: [
            {
              source: "02.md",
              document_name: "02.md",
              title: "Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
              page: null,
              topic: null,
              document_type: null,
              passage: "Cover crops and residue can support water holding.",
              relevance_score: 0.8,
              origin: "knowledge_base",
            },
          ],
        },
        { ...EMPTY_LAND_DETAILS, crop: "wheat", farm_size: "5 acres" },
      ),
    );
    const text = extractPdfText(doc);
    expect(text).toContain("AARANYA");
    expect(text).toContain("1. Site Profile");
    expect(text).toContain("2. Assessment Summary");
    expect(text).toContain("3. What to investigate first");
    expect(text).toContain("4. Recommendations");
    expect(text).toContain("5. Why these work together");
    expect(text).toContain("6. Next steps");
    expect(text).toContain("7. Sources / Evidence");
    expect(text).toContain("8. Monitoring Checklist");
    expect(text).toContain("9. Uncertainty");
    expect(text).toContain("Your 5 acre wheat field");
    expect(text).toContain("Drought-tolerant cover");
    expect(text).not.toMatch(/Y o u r 5 a c r e/);
    expect(text).not.toMatch(/D r o u g h t/);
    expect(text).not.toMatch(/## /);
    expect(text).not.toContain("**");
    expect(text).not.toMatch(/\|---/);
    expect(text).not.toMatch(/\|\s*Intervention\s*\|/);
    expect(text).toContain("Measure SOC");
    expect(text).toContain("Cover crops");
    expect(text).toContain("Intervention");
    expect(text).toContain("What to do");
    expect(text).toContain("Potentially affected metrics");
    expect(text).toContain("Time horizon");
    expect((text.match(/4\. Recommendations/g) || []).length).toBe(1);
    expect((text.match(/7\. Sources \/ Evidence/g) || []).length).toBe(1);
    expect((text.match(/9\. Uncertainty/g) || []).length).toBe(1);
    expect(extractPdfCharSpaces(doc).every((value) => value === 0)).toBe(true);
    expect(extractPdfWordSpaces(doc).every((value) => value === 0)).toBe(true);
    expect(text).not.toMatch(/C o v e r/);
  });

  it("normalizes inline ATX headings and keeps normal character spacing", async () => {
    const assistantMessage = [
      "Your 5 acre wheat field sits in a semi-arid zone with low, irregular rainfall. The soil dries quickly, suggesting limited water holding capacity. ## What to investigate first",
      "1. **Measure soil organic carbon**: A baseline SOC value will tell you how much carbon input is needed.",
      "2. **Monitor soil moisture dynamics**: Install a simple moisture probe.",
      "3. **Assess current cover crop or residue presence**: Determine whether living cover exists.",
      "",
      "## Recommendations",
      "| Intervention | What to do | Why it may help | Metrics | Time |",
      "|---|---|---|---|---|",
      "| Cover crops | Plant a drought-tolerant cover crop | Adds organic matter and living roots | SOC, soil moisture | Several seasons |",
    ].join("\n");
    const sections = planSections({ ...baseResponse, assistant_message: assistantMessage });
    expect(sections.assessment_summary).toContain("Your 5 acre wheat field sits in a semi-arid zone");
    expect(sections.assessment_summary).not.toContain("##");
    expect(sections.assessment_summary).not.toContain("What to investigate first");
    expect(sections.investigate_first).toContain("Measure soil organic carbon");
    expect(sections.investigate_first).not.toContain("##");

    const doc = await renderActionPlanPdf(
      buildActionPlan(
        {
          ...baseResponse,
          mode: "recommendation",
          assistant_message: assistantMessage,
          recommendation: {
            action: "Plant a drought-tolerant cover crop.",
            why_it_works: "Adds organic matter and living roots.",
            environmental_relationships: "Cover crops can support soil carbon.",
            impacted_metrics: [{ name: "Soil organic carbon", direction: "unknown", note: "potentially affected" }],
            time_horizon: { narrative: "Several seasons to multiple years", evidence_supported: true },
            uncertainty: "Local trials are still needed.",
            confidence: "medium",
            confidence_rationale: "Retrieved passages were available.",
            items: [
              {
                action: "Plant a drought-tolerant cover crop.",
                why: "Adds organic matter and living roots.",
                impacted_metrics: [{ name: "Soil organic carbon", direction: "unknown", note: "potentially affected" }],
                time_horizon: "Several seasons to multiple years",
                supporting_evidence: ["Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming"],
              },
            ],
          },
        },
        { ...EMPTY_LAND_DETAILS, crop: "wheat", farm_size: "5 acres" },
      ),
    );
    const text = extractPdfText(doc);
    expect(text).toContain("2. Assessment Summary");
    expect(text).toContain("Your 5 acre wheat field sits in a semi-arid zone with low, irregular rainfall.");
    expect(text).toContain("What to investigate first");
    expect(text).toContain("Measure soil organic carbon");
    expect(text).toContain("A baseline SOC value will tell you how much carbon input is needed.");
    expect(text).toContain("Monitor soil moisture dynamics");
    expect(text).toContain("Install a simple moisture probe.");
    expect(text).toContain("Assess current cover crop or residue presence");
    expect(text).toContain("Determine whether living cover exists.");
    expect(text).toContain("Intervention");
    expect(text).toContain("What to do");
    expect(text).toContain("Cover crops");
    expect(text).toContain("drought-tolerant cover crop");
    expect(text).not.toMatch(/Y o u r/);
    expect(text).not.toMatch(/D r o u g h t/);
    expect(text).not.toContain("##");
    expect(text).not.toContain("###");
    expect(text).not.toContain("**");
    expect(text).not.toMatch(/\|---/);
    expect(text).not.toMatch(/\|\s*Intervention\s*\|/);
    expect(extractPdfCharSpaces(doc).every((value) => value === 0)).toBe(true);
    expect(extractPdfWordSpaces(doc).every((value) => value === 0)).toBe(true);
  });
});
