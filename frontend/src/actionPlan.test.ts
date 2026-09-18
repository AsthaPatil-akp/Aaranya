import { describe, expect, it } from "vitest";
import { buildActionPlan } from "./actionPlan";
import { renderActionPlanPdf } from "./actionPlanPdf";
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

  it("renders a PDF for sparse and complete plans", () => {
    const sparse = renderActionPlanPdf(buildActionPlan(baseResponse, EMPTY_LAND_DETAILS));
    expect(sparse.output("arraybuffer").byteLength).toBeGreaterThan(500);
    const complete = renderActionPlanPdf(
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
    expect(complete.getNumberOfPages()).toBeGreaterThanOrEqual(1);
    expect(complete.output("arraybuffer").byteLength).toBeGreaterThan(sparse.output("arraybuffer").byteLength);
  });

  it("renders recommendation markdown as a PDF table without pipe syntax", () => {
    const doc = renderActionPlanPdf(
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
    const text = new TextDecoder("latin1").decode(doc.output("arraybuffer"));
    expect(text).not.toMatch(/\|\s*Action\s*\|/);
    expect(text).not.toMatch(/kb-14/);
    expect(text).toContain("Keep residue");
  });
});
