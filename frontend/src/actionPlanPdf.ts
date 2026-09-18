import { PDFDocument, PDFFont, PDFPage, RGB, StandardFonts, rgb } from "pdf-lib";
import { buildActionPlan, ActionPlanDocument, ActionPlanRecommendation } from "./actionPlan";
import { ChatResponse } from "./api";
import { LandDetails } from "./landDetails";
import {
  normalizePdfText,
  parsePdfBlocks,
  normalizeRecommendationTable,
  PdfBlock,
} from "./pdfMarkdown";

const FOREST = rgb(27 / 255, 67 / 255, 50 / 255);
const INK = rgb(32 / 255, 36 / 255, 32 / 255);
const MUTED = rgb(90 / 255, 96 / 255, 88 / 255);
const RULE = rgb(214 / 255, 204 / 255, 184 / 255);
const ACCENT = rgb(196 / 255, 162 / 255, 90 / 255);
const CREAM = rgb(252 / 255, 249 / 255, 243 / 255);
const ALT = rgb(247 / 255, 242 / 255, 232 / 255);

const PAGE_W = 841.89;
const PAGE_H = 595.28;
const MARGIN = 40;
const CONTENT_W = PAGE_W - MARGIN * 2;
const TOP = PAGE_H - 36;
const BOTTOM = 28;

function pdfSafe(text: string): string {
  return normalizePdfText(String(text || ""))
    .replace(/[^\u0009\u000A\u000D\u0020-\u00FF]/g, " ")
    .replace(/[ \t]+/g, " ")
    .trim();
}

function wrapText(font: PDFFont, text: string, size: number, width: number): string[] {
  const source = pdfSafe(text);
  if (!source) return [];
  const words = source.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const trial = current ? `${current} ${word}` : word;
    if (font.widthOfTextAtSize(trial, size) <= width) {
      current = trial;
      continue;
    }
    if (current) lines.push(current);
    if (font.widthOfTextAtSize(word, size) <= width) {
      current = word;
      continue;
    }
    let chunk = "";
    for (const char of word) {
      const next = chunk + char;
      if (chunk && font.widthOfTextAtSize(next, size) > width) {
        lines.push(chunk);
        chunk = char;
      } else {
        chunk = next;
      }
    }
    current = chunk;
  }
  if (current) lines.push(current);
  return lines;
}

function decodePdfString(raw: string): string {
  const chunks: string[] = [];
  const tj = /\((?:\\.|[^\\)])*\)\s*Tj/g;
  let match: RegExpExecArray | null;
  while ((match = tj.exec(raw))) {
    chunks.push(
      match[0]
        .replace(/\s*Tj$/, "")
        .replace(/^\(|\)$/g, "")
        .replace(/\\n/g, "\n")
        .replace(/\\[()\\]/g, (token) => token.slice(1)),
    );
  }
  return chunks.join("\n");
}

export function extractPdfText(doc: { text: string } | Uint8Array): string {
  if (doc instanceof Uint8Array) {
    return decodePdfString(new TextDecoder("latin1").decode(doc));
  }
  return doc.text;
}

export function extractPdfCharSpaces(doc: { bytes: Uint8Array } | Uint8Array): number[] {
  const bytes = doc instanceof Uint8Array ? doc : doc.bytes;
  const raw = new TextDecoder("latin1").decode(bytes);
  return [...raw.matchAll(/([-+]?(?:\d+\.?\d*|\.\d+))\s+Tc/g)].map((match) => Number(match[1]));
}

export function extractPdfWordSpaces(doc: { bytes: Uint8Array } | Uint8Array): number[] {
  const bytes = doc instanceof Uint8Array ? doc : doc.bytes;
  const raw = new TextDecoder("latin1").decode(bytes);
  return [...raw.matchAll(/([-+]?(?:\d+\.?\d*|\.\d+))\s+Tw/g)].map((match) => Number(match[1]));
}

export type ActionPlanPdf = {
  bytes: Uint8Array;
  pageCount: number;
  text: string;
};

export async function renderActionPlanPdf(plan: ActionPlanDocument): Promise<ActionPlanPdf> {
  const doc = await PDFDocument.create();
  const regular = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);
  const italic = await doc.embedFont(StandardFonts.HelveticaOblique);
  const pages: PDFPage[] = [];
  const drawn: string[] = [];
  let page = doc.addPage([PAGE_W, PAGE_H]);
  pages.push(page);
  let y = TOP;

  const addPage = () => {
    page = doc.addPage([PAGE_W, PAGE_H]);
    pages.push(page);
    y = TOP - 8;
  };

  const ensure = (needed: number) => {
    if (y - needed >= BOTTOM) return;
    addPage();
  };

  const drawText = (text: string, x: number, pos: number, size: number, font: PDFFont, color: RGB) => {
    const line = pdfSafe(text);
    if (!line) return;
    drawn.push(line);
    page.drawText(line, { x, y: pos, size, font, color });
  };

  const wrapped = (
    text: string,
    options?: { font?: PDFFont; size?: number; color?: RGB; indent?: number; width?: number; gap?: number },
  ) => {
    const font = options?.font ?? regular;
    const size = options?.size ?? 10;
    const color = options?.color ?? INK;
    const indent = options?.indent ?? 0;
    const width = options?.width ?? CONTENT_W - indent;
    const gap = options?.gap ?? 13;
    const lines = wrapText(font, text, size, width);
    for (const line of lines) {
      ensure(gap);
      drawText(line, MARGIN + indent, y, size, font, color);
      y -= gap;
    }
  };

  const muted = (text: string) => wrapped(text, { font: italic, size: 9, color: MUTED, gap: 12 });

  const section = (title: string) => {
    ensure(28);
    y -= 8;
    page.drawRectangle({ x: MARGIN, y: y - 2, width: 6, height: 14, color: FOREST });
    drawText(title, MARGIN + 12, y, 13, bold, FOREST);
    y -= 20;
  };

  const writeBlocks = (blocks: PdfBlock[], emptyMessage: string) => {
    if (!blocks.length) {
      muted(emptyMessage);
      return;
    }
    for (const block of blocks) {
      if (block.type === "heading") {
        ensure(24);
        y -= 4;
        page.drawRectangle({ x: MARGIN, y: y - 2, width: 6, height: 14, color: FOREST });
        drawText(block.text, MARGIN + 12, y, 13, bold, FOREST);
        y -= 20;
        continue;
      }
      if (block.type === "paragraph") {
        wrapped(block.text);
        y -= 4;
        continue;
      }
      if (block.type === "unordered-list") {
        for (const item of block.items) {
          const lines = wrapText(regular, item, 10, CONTENT_W - 16);
          ensure(14 + lines.length * 13);
          drawText("-", MARGIN, y, 10, regular, INK);
          lines.forEach((line) => {
            ensure(13);
            drawText(line, MARGIN + 14, y, 10, regular, INK);
            y -= 13;
          });
          y -= 4;
        }
        continue;
      }
      block.items.forEach((item, index) => {
        const title = `${index + 1}. ${item.title}`.trim();
        wrapped(title, { font: bold, size: 10, gap: 13 });
        if (item.body) wrapped(item.body, { size: 10, indent: 16, gap: 13 });
        y -= 6;
      });
    }
  };

  const drawTable = (rows: string[][]) => {
    if (!rows.length) {
      muted("No recommendations were returned for this response.");
      return;
    }
    const headers = ["Intervention", "What to do", "Why it may help", "Potentially affected metrics", "Time horizon"];
    const fractions = [0.15, 0.24, 0.26, 0.19, 0.16];
    const widths = fractions.map((part) => CONTENT_W * part);
    const pad = 6;
    const size = 8;

    const cellLines = (text: string, width: number, font: PDFFont) =>
      wrapText(font, text, size, Math.max(24, width - pad * 2));

    const rowHeight = (cells: string[], header = false) => {
      const font = header ? bold : regular;
      const lines = Math.max(1, ...cells.map((cell, index) => cellLines(cell, widths[index], index === 0 || header ? bold : font).length));
      return Math.max(28, lines * 11 + 10);
    };

    const paintRow = (cells: string[], header: boolean, fill: RGB) => {
      const height = rowHeight(cells, header);
      ensure(height + 2);
      let x = MARGIN;
      cells.forEach((cell, index) => {
        const width = widths[index];
        page.drawRectangle({
          x,
          y: y - height + 8,
          width,
          height,
          color: fill,
          borderColor: RULE,
          borderWidth: 0.6,
        });
        const font = header || index === 0 ? bold : regular;
        const color = header ? CREAM : INK;
        const lines = cellLines(cell, width, font);
        let textY = y - 6;
        for (const line of lines) {
          drawText(line, x + pad, textY, size, font, color);
          textY -= 11;
        }
        x += width;
      });
      y -= height;
    };

    paintRow(headers, true, FOREST);
    rows.forEach((row, index) => paintRow(row, false, index % 2 ? ALT : CREAM));
    y -= 10;
  };

  page.drawRectangle({ x: 0, y: PAGE_H - 64, width: PAGE_W, height: 64, color: FOREST });
  page.drawRectangle({ x: 0, y: PAGE_H - 68, width: PAGE_W, height: 4, color: ACCENT });
  drawText(pdfSafe(plan.heading), MARGIN, PAGE_H - 38, 18, bold, CREAM);
  drawText(pdfSafe(plan.generatedLabel), MARGIN, PAGE_H - 54, 10, regular, CREAM);
  y = PAGE_H - 86;

  section("1. Site Profile");
  if (!plan.siteProfile.length) {
    muted("No land details were provided for this response.");
  } else {
    for (const row of plan.siteProfile) {
      const valueLines = wrapText(regular, row.value, 10, CONTENT_W - 150);
      ensure(14 + Math.max(0, valueLines.length - 1) * 12);
      drawText(pdfSafe(row.label), MARGIN, y, 10, bold, FOREST);
      if (!valueLines.length) {
        y -= 14;
        continue;
      }
      valueLines.forEach((line, index) => {
        if (index > 0) ensure(12);
        drawText(line, MARGIN + 150, y, 10, regular, INK);
        y -= 14;
      });
    }
  }

  section("2. Assessment Summary");
  writeBlocks(parsePdfBlocks(plan.assessment), "No grounded assessment text was returned.");

  section("3. What to investigate first");
  writeBlocks(parsePdfBlocks(plan.investigateFirst), "No investigation steps were returned.");

  section("4. Recommendations");
  const fallbackRows = (plan.recommendations || []).map((item: ActionPlanRecommendation) => {
    const action = item.action || "";
    const firstClause = action.split(/[.]/, 1)[0].trim();
    return [
      firstClause && firstClause.length <= 48 ? firstClause : action,
      action,
      item.why || "",
      item.metrics.map((metric) => `${metric.name}: ${metric.note || "potentially affected"}`).join("; "),
      item.timeHorizon || "",
    ];
  });
  const table = normalizeRecommendationTable(plan.recommendationTable, fallbackRows);
  drawTable(table.rows);

  section("5. Why these work together");
  writeBlocks(parsePdfBlocks(plan.whyTogether), "No combined-explanation text was returned.");

  section("6. Next steps");
  writeBlocks(parsePdfBlocks(plan.nextSteps), "No next steps were returned.");

  section("7. Sources / Evidence");
  if (!plan.kbSources.length && !plan.externalSources.length) {
    muted("No supporting sources were used in the grounded response.");
  }
  if (plan.kbSources.length) {
    wrapped("Internal knowledge base", { font: bold, color: FOREST });
    for (const source of plan.kbSources) {
      wrapped(`${source.title} - ${source.evidenceLevel}${source.link ? `. ${source.link}` : ""}`);
    }
  }
  if (plan.externalSources.length) {
    wrapped("External scientific sources", { font: bold, color: FOREST });
    for (const source of plan.externalSources) {
      wrapped(`${source.title} - ${source.evidenceLevel}${source.link ? `. ${source.link}` : ""}`);
    }
  } else if (plan.kbSources.length) {
    muted("No external scientific sources were used.");
  }

  section("8. Monitoring Checklist");
  if (!plan.monitoring.length) {
    muted("No impacted metrics were returned to monitor.");
  } else {
    for (const item of plan.monitoring) {
      ensure(28);
      page.drawRectangle({
        x: MARGIN,
        y: y - 2,
        width: 9,
        height: 9,
        borderColor: FOREST,
        borderWidth: 1,
      });
      wrapped(`Monitor ${item.metric}`, { indent: 16 });
      const freq = item.frequency
        ? `Suggested observation frequency: ${item.frequency}`
        : "Suggested observation frequency: ";
      wrapped(freq, { size: 9, color: MUTED, indent: 16 });
      y -= 4;
    }
  }

  section("9. Uncertainty");
  if (!plan.limitations.length) muted("No additional uncertainty statement was returned.");
  else plan.limitations.forEach((line) => writeBlocks(parsePdfBlocks(line), ""));

  const total = pages.length;
  pages.forEach((footerPage, index) => {
    footerPage.drawLine({
      start: { x: MARGIN, y: 18 },
      end: { x: PAGE_W - MARGIN, y: 18 },
      thickness: 0.6,
      color: RULE,
    });
    footerPage.drawText("Grounded evidence only. Missing values are left blank.", {
      x: MARGIN,
      y: 8,
      size: 8,
      font: regular,
      color: MUTED,
    });
    const label = `${index + 1} / ${total}`;
    footerPage.drawText(label, {
      x: PAGE_W - MARGIN - regular.widthOfTextAtSize(label, 8),
      y: 8,
      size: 8,
      font: regular,
      color: MUTED,
    });
  });

  const bytes = await doc.save({ useObjectStreams: false });
  return { bytes, pageCount: total, text: drawn.join("\n") };
}

export async function downloadActionPlanPdf(response: ChatResponse, landDetails: LandDetails) {
  const plan = buildActionPlan(response, landDetails);
  const pdf = await renderActionPlanPdf(plan);
  const stamp = new Date().toISOString().slice(0, 10);
  const blob = new Blob([Uint8Array.from(pdf.bytes)], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `aaranya-biodiversity-action-plan-${stamp}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}
