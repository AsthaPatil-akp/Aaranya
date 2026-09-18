import { describe, expect, it } from "vitest";
import { parsePdfBlocks, stripMarkdownSyntax } from "./pdfMarkdown";

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
});
