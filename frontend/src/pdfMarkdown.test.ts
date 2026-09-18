import { describe, expect, it } from "vitest";
import { parsePdfBlocks, splitInlineAtxHeadings, stripMarkdownSyntax } from "./pdfMarkdown";

const INLINE_HEADING_SAMPLE = [
  "Your 5 acre wheat field sits in a semi-arid zone with low, irregular rainfall. The soil dries quickly, suggesting limited water holding capacity. ## What to investigate first",
  "1. **Measure soil organic carbon**: A baseline SOC value will tell you how much carbon input is needed.",
  "2. **Monitor soil moisture dynamics**: Install a simple moisture probe.",
  "3. **Assess current cover crop or residue presence**: Determine whether living cover exists.",
].join("\n");

describe("PDF markdown parsing", () => {
  it("strips markdown markers without leaving hashes or asterisks", () => {
    expect(stripMarkdownSyntax("## Next steps")).toBe("Next steps");
    expect(stripMarkdownSyntax("**bold text**")).toBe("bold text");
  });

  it("splits numbered items that were run together", () => {
    const blocks = parsePdfBlocks(
      "1. Measure SOC and soil moisture. 2. Map current intercropping patterns. 3. Assess residue retention.",
    );
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("ordered-list");
    if (blocks[0].type !== "ordered-list") return;
    expect(blocks[0].items).toHaveLength(3);
    expect(blocks[0].items[0].title).toMatch(/Measure SOC/i);
    expect(blocks[0].items[1].title).toMatch(/intercropping/i);
    expect(blocks[0].items[2].title).toMatch(/residue/i);
  });

  it("keeps list titles separate from following explanations", () => {
    const blocks = parsePdfBlocks(
      [
        "1. **Measure SOC** - Determine whether SOC is low, moderate, or high.",
        "",
        "2. **Assess soil moisture** - Monitor how quickly the soil dries.",
      ].join("\n"),
    );
    expect(blocks[0].type).toBe("ordered-list");
    if (blocks[0].type !== "ordered-list") return;
    expect(blocks[0].items[0]).toEqual({
      title: "Measure SOC",
      body: "Determine whether SOC is low, moderate, or high.",
    });
    expect(blocks[0].items[1].title).toBe("Assess soil moisture");
  });

  it("drops leftover numbered markers like '3. 3.'", () => {
    const blocks = parsePdfBlocks("1. Measure SOC\n2. Soil moisture\n3. 3\n3. Existing cover crop or residue use");
    expect(blocks[0].type).toBe("ordered-list");
    if (blocks[0].type !== "ordered-list") return;
    expect(blocks[0].items.map((item) => item.title)).toEqual([
      "Measure SOC",
      "Soil moisture",
      "Existing cover crop or residue use",
    ]);
  });

  it("splits inline ATX headings without touching URLs or C# tokens", () => {
    const split = splitInlineAtxHeadings(
      "Low soil organic carbon can reduce biodiversity. ## What to investigate first\nSee https://example.com/path#section and C# notes. ### Soil notes",
    );
    expect(split).toContain(".\n\n## What to investigate first");
    expect(split).toContain(".\n\n### Soil notes");
    expect(split).toContain("https://example.com/path#section");
    expect(split).toContain("C# notes");
    expect(splitInlineAtxHeadings(" ## Recommendations")).toBe(" ## Recommendations");
  });

  it("parses a mid-line markdown heading as a heading plus formatted list items", () => {
    const blocks = parsePdfBlocks(INLINE_HEADING_SAMPLE);
    expect(blocks.map((block) => block.type)).toEqual(["paragraph", "heading", "ordered-list"]);
    expect(blocks[0]).toEqual({
      type: "paragraph",
      text: "Your 5 acre wheat field sits in a semi-arid zone with low, irregular rainfall. The soil dries quickly, suggesting limited water holding capacity.",
    });
    expect(blocks[1]).toEqual({ type: "heading", text: "What to investigate first" });
    if (blocks[2].type !== "ordered-list") return;
    expect(blocks[2].items).toEqual([
      {
        title: "Measure soil organic carbon",
        body: "A baseline SOC value will tell you how much carbon input is needed.",
      },
      {
        title: "Monitor soil moisture dynamics",
        body: "Install a simple moisture probe.",
      },
      {
        title: "Assess current cover crop or residue presence",
        body: "Determine whether living cover exists.",
      },
    ]);
    const serialized = JSON.stringify(blocks);
    expect(serialized).not.toContain("##");
    expect(serialized).not.toContain("**");
    expect(serialized).not.toContain("|");
  });
});
