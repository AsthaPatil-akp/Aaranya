import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownMessage } from "./components/MarkdownMessage";
import {
  extractAnswerSections,
  hideInternalEvidenceIds,
  normalizeChatMarkdown,
  parseMarkdownTables,
  stripMarkdownTables,
} from "./markdown";

describe("markdown helpers", () => {
  it("replaces leftover internal ids and parses GFM tables", () => {
    const text = hideInternalEvidenceIds("See kb-6 and kb-14 for residue.", {
      "kb-6": "Monoculture, Agroforestry and Habitat Complexity",
    });
    expect(text).not.toMatch(/kb-6|kb-14/);
    expect(text).toContain("Monoculture, Agroforestry and Habitat Complexity");
    const tables = parseMarkdownTables(
      "| Action | Why |\n| --- | --- |\n| Keep residue | Supports cover |\n",
    );
    expect(tables).toHaveLength(1);
    expect(tables[0].headers).toEqual(["Action", "Why"]);
    expect(tables[0].rows[0]).toEqual(["Keep residue", "Supports cover"]);
    expect(stripMarkdownTables("| Action | Why |\n| --- | --- |\n| Keep residue | Supports cover |\n")).toBe("");
  });

  it("keeps assessment separate from an unheaded table", () => {
    const sections = extractAnswerSections(
      "Low carbon and rainfall interact.\n\n| Action | Why |\n| --- | --- |\n| Cover crops | Moisture |\n\n## Sources / Evidence\n- Cover Crops\n",
    );
    expect(sections.assessment_summary).toContain("Low carbon");
    expect(sections.assessment_summary).not.toContain("|");
    expect(sections.recommendations).toContain("Cover crops");
  });
});

describe("MarkdownMessage", () => {
  it("renders a markdown table as an HTML table and hides internal ids", () => {
    render(
      <MarkdownMessage
        text={
          "## Recommendations\n\n| Action | Evidence |\n| --- | --- |\n| Keep residue | kb-18 |\n\nSee [Cover Crops](https://example.org/cover)."
        }
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Action" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Keep residue" })).toBeInTheDocument();
    expect(screen.queryByText(/kb-18/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\| Action \|/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cover Crops" })).toHaveAttribute("href", "https://example.org/cover");
  });

  it("renders headings, bold text, numbered lists, and GFM tables from assistant markdown", () => {
    const sample = `## Recommendations

1. **Measure SOC** – Determine whether SOC is low, moderate, or high.

2. **Assess soil moisture** – Monitor how quickly the soil dries.

### Recommended actions

| Intervention | What to do | Why it may help | Metrics |
|---|---|---|---|
| Cover crops | Plant a drought-tolerant cover crop | Adds organic matter and living roots | SOC, soil moisture |
| Agroforestry | Add widely spaced trees/shrubs | Provides habitat and wind protection | SOC, habitat |
| Flowering strips | Add flowering plants | Provides pollinator resources | Pollinator activity |
`;
    render(<MarkdownMessage text={sample} />);
    expect(screen.getByTestId("assistant-markdown")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Recommendations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Recommended actions" })).toBeInTheDocument();
    expect(screen.getByText("Measure SOC").tagName).toBe("STRONG");
    expect(screen.getByText("Assess soil moisture").tagName).toBe("STRONG");
    expect(screen.queryByText("**Measure SOC**")).not.toBeInTheDocument();
    expect(screen.getByText(/Determine whether SOC is low/).closest("li")).toBeTruthy();
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Intervention" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Cover crops" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Agroforestry" })).toBeInTheDocument();
    expect(screen.queryByText(/\| Intervention \|/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\|---/)).not.toBeInTheDocument();
  });

  it("splits run-on lists, stuck headings, and leftover internal ids", () => {
    render(
      <MarkdownMessage
        text={
          "## What is agroforestry? Agroforestry is trees with crops. - **Habitat:** birds - **Soil health:** litter See kb-99 leftover."
        }
      />,
    );
    expect(screen.getByRole("heading", { name: /what is agroforestry/i })).toBeInTheDocument();
    expect(screen.getByText(/Agroforestry is trees with crops/)).toBeInTheDocument();
    expect(screen.getByText("Habitat:").tagName).toBe("STRONG");
    expect(screen.getByText("Soil health:").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/kb-99/)).not.toBeInTheDocument();
  });
});

describe("normalizeChatMarkdown", () => {
  it("keeps one Recommendations heading and splits numbered items", () => {
    const text = normalizeChatMarkdown(
      "Start here. ## Recommendations 1. Cover crops. 2. Native trees. ## Recommendations",
    );
    expect(text.toLowerCase().split("## recommendations").length - 1).toBe(1);
    expect(text).toContain("1. Cover crops.");
    expect(text).toContain("2. Native trees.");
    expect(text).not.toMatch(/1\. Cover crops\. 2\./);
    expect(text).toMatch(/1\. Cover crops\.\s+2\. Native trees\./);
  });
});
