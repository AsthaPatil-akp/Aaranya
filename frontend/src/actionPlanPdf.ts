import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import { buildActionPlan, ActionPlanDocument, ActionPlanRecommendation } from "./actionPlan";
import { ChatResponse } from "./api";
import { LandDetails } from "./landDetails";
import {
  normalizePdfText,
  parsePdfBlocks,
  normalizeRecommendationTable,
  PdfBlock,
} from "./pdfMarkdown";

const FOREST: [number, number, number] = [27, 67, 50];
const INK: [number, number, number] = [32, 36, 32];
const MUTED: [number, number, number] = [90, 96, 88];
const RULE: [number, number, number] = [214, 204, 184];
const ACCENT: [number, number, number] = [196, 162, 90];
const CREAM: [number, number, number] = [252, 249, 243];

const MARGIN = 14;
const PAGE_W = 297;
const PAGE_H = 210;
const CONTENT_W = PAGE_W - MARGIN * 2;
const FOOTER_Y = PAGE_H - 10;
const BOTTOM = PAGE_H - 16;

function asLines(value: unknown): string[] {
  if (value == null || value === "") return [];
  if (Array.isArray(value)) return value.map((item) => String(item));
  return [String(value)];
}

function wrap(doc: jsPDF, text: string, width = CONTENT_W): string[] {
  const source = normalizePdfText(String(text || "")).replace(/[ \t]+/g, " ").trim();
  if (!source) return [];
  const wrapped = doc.splitTextToSize(source, Math.max(20, width));
  const lines = asLines(wrapped)
    .map((line) => normalizePdfText(String(line)))
    .filter((line) => line.length > 0);
  if (lines.length > 3 && lines.every((line) => line.length === 1)) {
    const joined = lines.join("");
    if (joined === source) return [joined];
    return wrap(doc, joined, width);
  }
  return lines;
}

function writePdfOperators(doc: jsPDF, operators: string[]) {
  const write = (doc.internal as { write?: (...parts: string[]) => void }).write;
  if (typeof write !== "function") return;
  for (const operator of operators) write.call(doc.internal, operator);
}

function resetTextState(doc: jsPDF) {
  // setCharSpace() only updates JS state; PDF Tc/Tw persist across BT/ET.
  // Write the operators into the content stream so later text cannot inherit
  // leaked letter- or word-spacing. Never pass charSpace into doc.text().
  doc.setCharSpace(0);
  writePdfOperators(doc, ["0 Tc", "0 Tw"]);
}

function writeLine(doc: jsPDF, text: string, x: number, y: number) {
  const line = normalizePdfText(String(text ?? ""));
  if (!line) return;
  resetTextState(doc);
  doc.text(line, x, y);
}

function writeRight(doc: jsPDF, text: string, rightX: number, y: number) {
  const line = normalizePdfText(String(text ?? ""));
  if (!line) return;
  const width = (doc.getStringUnitWidth(line) * doc.getFontSize()) / doc.internal.scaleFactor;
  writeLine(doc, line, rightX - width, y);
}

function addFooter(doc: jsPDF, page: number, total: number) {
  doc.setDrawColor(...RULE);
  doc.setLineWidth(0.3);
  doc.line(MARGIN, FOOTER_Y - 4, PAGE_W - MARGIN, FOOTER_Y - 4);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  writeLine(doc, "Grounded evidence only. Missing values are left blank.", MARGIN, FOOTER_Y);
  writeRight(doc, `${page} / ${total}`, PAGE_W - MARGIN, FOOTER_Y);
}

export function extractPdfText(doc: jsPDF): string {
  const raw = new TextDecoder("latin1").decode(doc.output("arraybuffer"));
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

export function extractPdfCharSpaces(doc: jsPDF): number[] {
  const raw = new TextDecoder("latin1").decode(doc.output("arraybuffer"));
  return [...raw.matchAll(/([-+]?(?:\d+\.?\d*|\.\d+))\s+Tc/g)].map((match) => Number(match[1]));
}

export function extractPdfWordSpaces(doc: jsPDF): number[] {
  const raw = new TextDecoder("latin1").decode(doc.output("arraybuffer"));
  return [...raw.matchAll(/([-+]?(?:\d+\.?\d*|\.\d+))\s+Tw/g)].map((match) => Number(match[1]));
}

export function renderActionPlanPdf(plan: ActionPlanDocument): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "a4", orientation: "landscape" });
  resetTextState(doc);
  doc.setLineHeightFactor(1.25);
  let y = 0;

  const ensure = (needed: number) => {
    if (y + needed <= BOTTOM) return;
    doc.addPage();
    y = 18;
    resetTextState(doc);
  };

  const section = (title: string, minBody = 14) => {
    ensure(12 + minBody);
    y += 3;
    doc.setFillColor(...FOREST);
    doc.rect(MARGIN, y, 2.2, 6.2, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    resetTextState(doc);
    doc.setTextColor(...FOREST);
    writeLine(doc, title, MARGIN + 6, y + 5);
    y += 11;
  };

  const writeWrapped = (text: string, options?: { italic?: boolean; size?: number; color?: [number, number, number]; indent?: number; width?: number; gap?: number }) => {
    const indent = options?.indent ?? 0;
    const width = options?.width ?? CONTENT_W - indent;
    const lines = wrap(doc, text, width);
    doc.setFont("helvetica", options?.italic ? "italic" : "normal");
    doc.setFontSize(options?.size ?? 10);
    resetTextState(doc);
    doc.setTextColor(...(options?.color ?? INK));
    for (const line of lines) {
      ensure(6);
      writeLine(doc, line, MARGIN + indent, y);
      y += options?.gap ?? 5;
    }
  };

  const muted = (text: string) => writeWrapped(text, { italic: true, size: 9, color: MUTED, gap: 4.8 });

  const writeBlocks = (blocks: PdfBlock[], emptyMessage: string) => {
    if (!blocks.length) {
      muted(emptyMessage);
      return;
    }
    for (const block of blocks) {
      if (block.type === "heading") {
        ensure(14);
        y += 2;
        doc.setFillColor(...FOREST);
        doc.rect(MARGIN, y, 2.2, 6.2, "F");
        doc.setFont("helvetica", "bold");
        doc.setFontSize(12);
        resetTextState(doc);
        doc.setTextColor(...FOREST);
        writeLine(doc, block.text, MARGIN + 6, y + 5);
        y += 11;
        continue;
      }
      if (block.type === "paragraph") {
        writeWrapped(block.text);
        y += 1.5;
        continue;
      }
      if (block.type === "unordered-list") {
        for (const item of block.items) {
          const lines = wrap(doc, item, CONTENT_W - 8);
          ensure(6 + lines.length * 5);
          doc.setFont("helvetica", "normal");
          doc.setFontSize(10);
          resetTextState(doc);
          doc.setTextColor(...INK);
          writeLine(doc, "-", MARGIN, y);
          lines.forEach((line, index) => {
            if (index > 0) ensure(5);
            writeLine(doc, line, MARGIN + 6, y);
            y += 5;
          });
          y += 1.2;
        }
        y += 1;
        continue;
      }
      block.items.forEach((item, index) => {
        const title = `${index + 1}. ${item.title}`.trim();
        const titleLines = wrap(doc, title, CONTENT_W - 6);
        const bodyLines = item.body ? wrap(doc, item.body, CONTENT_W - 10) : [];
        ensure(8 + (titleLines.length + bodyLines.length) * 5);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(10);
        resetTextState(doc);
        doc.setTextColor(...INK);
        titleLines.forEach((line, lineIndex) => {
          if (lineIndex > 0) ensure(5);
          writeLine(doc, line, MARGIN, y);
          y += 5;
        });
        if (bodyLines.length) {
          doc.setFont("helvetica", "normal");
          bodyLines.forEach((line) => {
            ensure(5);
            writeLine(doc, line, MARGIN + 7, y);
            y += 5;
          });
        }
        y += 3;
      });
    }
  };

  const checkbox = (label: string, extra?: string) => {
    const lines = wrap(doc, label, CONTENT_W - 8);
    const extraLines = extra ? wrap(doc, extra, CONTENT_W - 8) : [];
    ensure(8 + (lines.length + extraLines.length) * 4.8);
    doc.setDrawColor(...FOREST);
    doc.setLineWidth(0.35);
    doc.rect(MARGIN, y - 3.1, 3.4, 3.4);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    resetTextState(doc);
    doc.setTextColor(...INK);
    lines.forEach((line, index) => {
      if (index > 0) ensure(5);
      writeLine(doc, line, MARGIN + 7, y);
      y += 4.8;
    });
    y += 1;
    if (extraLines.length) {
      doc.setFontSize(9);
      doc.setTextColor(...MUTED);
      extraLines.forEach((line) => {
        ensure(5);
        writeLine(doc, line, MARGIN + 7, y);
        y += 4.6;
      });
      y += 1.5;
    }
  };

  const drawTable = (rows: string[][]) => {
    if (!rows.length) {
      muted("No recommendations were returned for this response.");
      return;
    }
    ensure(28);
    const usable = CONTENT_W;
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN, top: 18, bottom: 16 },
      tableWidth: usable,
      showHead: "everyPage",
      rowPageBreak: "avoid",
      theme: "grid",
      styles: {
        font: "helvetica",
        fontStyle: "normal",
        fontSize: 8,
        cellPadding: { top: 2.4, right: 2.6, bottom: 2.4, left: 2.6 },
        overflow: "linebreak",
        valign: "top",
        halign: "left",
        textColor: INK,
        lineColor: RULE,
        lineWidth: 0.2,
        minCellHeight: 9,
      },
      headStyles: {
        fillColor: FOREST,
        textColor: CREAM,
        fontStyle: "bold",
        fontSize: 8,
        overflow: "linebreak",
        valign: "top",
        halign: "left",
      },
      bodyStyles: {
        fillColor: CREAM,
      },
      alternateRowStyles: {
        fillColor: [247, 242, 232],
      },
      columnStyles: {
        0: { cellWidth: usable * 0.15, fontStyle: "bold" },
        1: { cellWidth: usable * 0.24 },
        2: { cellWidth: usable * 0.26 },
        3: { cellWidth: usable * 0.19 },
        4: { cellWidth: usable * 0.16 },
      },
      head: [["Intervention", "What to do", "Why it may help", "Potentially affected metrics", "Time horizon"]],
      body: rows,
    });
    const tableMeta = (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable;
    doc.setPage(doc.getNumberOfPages());
    y = (tableMeta?.finalY ?? y) + 8;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    resetTextState(doc);
    doc.setTextColor(...INK);
  };

  doc.setFillColor(...FOREST);
  doc.rect(0, 0, PAGE_W, 28, "F");
  doc.setFillColor(...ACCENT);
  doc.rect(0, 28, PAGE_W, 1.2, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  resetTextState(doc);
  doc.setTextColor(...CREAM);
  writeLine(doc, plan.heading, MARGIN, 14);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  writeLine(doc, plan.generatedLabel, MARGIN, 22);
  y = 36;

  section("1. Site Profile");
  if (!plan.siteProfile.length) {
    muted("No land details were provided for this response.");
  } else {
    for (const row of plan.siteProfile) {
      const valueLines = wrap(doc, row.value, CONTENT_W - 48);
      ensure(6 + Math.max(0, valueLines.length - 1) * 5);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      resetTextState(doc);
      doc.setTextColor(...FOREST);
      writeLine(doc, row.label, MARGIN, y);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...INK);
      if (!valueLines.length) {
        y += 5.2;
        continue;
      }
      writeLine(doc, valueLines[0], MARGIN + 48, y);
      y += 5.2;
      for (const extra of valueLines.slice(1)) {
        ensure(5.2);
        writeLine(doc, extra, MARGIN + 48, y);
        y += 5.2;
      }
    }
  }

  section("2. Assessment Summary");
  writeBlocks(parsePdfBlocks(plan.assessment), "No grounded assessment text was returned.");

  section("3. What to investigate first");
  writeBlocks(parsePdfBlocks(plan.investigateFirst), "No investigation steps were returned.");

  section("4. Recommendations", 24);
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
    ensure(10);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    resetTextState(doc);
    doc.setTextColor(...FOREST);
    writeLine(doc, "Internal knowledge base", MARGIN, y);
    y += 6;
    for (const source of plan.kbSources) {
      writeWrapped(`${source.title} - ${source.evidenceLevel}${source.link ? `. ${source.link}` : ""}`);
    }
  }
  if (plan.externalSources.length) {
    ensure(10);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    resetTextState(doc);
    doc.setTextColor(...FOREST);
    writeLine(doc, "External scientific sources", MARGIN, y);
    y += 6;
    for (const source of plan.externalSources) {
      writeWrapped(`${source.title} - ${source.evidenceLevel}${source.link ? `. ${source.link}` : ""}`);
    }
  } else if (plan.kbSources.length) {
    muted("No external scientific sources were used.");
  }

  section("8. Monitoring Checklist");
  if (!plan.monitoring.length) {
    muted("No impacted metrics were returned to monitor.");
  } else {
    for (const item of plan.monitoring) {
      const freq = item.frequency
        ? `Suggested observation frequency: ${item.frequency}`
        : "Suggested observation frequency: ";
      checkbox(`Monitor ${item.metric}`, freq);
    }
  }

  section("9. Uncertainty");
  if (!plan.limitations.length) muted("No additional uncertainty statement was returned.");
  else plan.limitations.forEach((line) => writeBlocks(parsePdfBlocks(line), ""));

  const total = doc.getNumberOfPages();
  for (let page = 1; page <= total; page += 1) {
    doc.setPage(page);
    addFooter(doc, page, total);
  }
  return doc;
}

export function downloadActionPlanPdf(response: ChatResponse, landDetails: LandDetails) {
  const plan = buildActionPlan(response, landDetails);
  const doc = renderActionPlanPdf(plan);
  const stamp = new Date().toISOString().slice(0, 10);
  doc.save(`aaranya-biodiversity-action-plan-${stamp}.pdf`);
}
