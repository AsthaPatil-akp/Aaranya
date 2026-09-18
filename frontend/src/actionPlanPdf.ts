import { jsPDF } from "jspdf";
import { buildActionPlan, ActionPlanDocument } from "./actionPlan";
import { MarkdownTable, stripMarkdownTables } from "./markdown";
import { ChatResponse } from "./api";
import { LandDetails } from "./landDetails";

const FOREST: [number, number, number] = [27, 67, 50];
const INK: [number, number, number] = [32, 36, 32];
const MUTED: [number, number, number] = [90, 96, 88];
const RULE: [number, number, number] = [214, 204, 184];
const ACCENT: [number, number, number] = [196, 162, 90];

const MARGIN = 18;
const PAGE_W = 210;
const PAGE_H = 297;
const CONTENT_W = PAGE_W - MARGIN * 2;

function wrap(doc: jsPDF, text: string, width = CONTENT_W): string[] {
  return doc.splitTextToSize(text || "", width) as string[];
}

function addFooter(doc: jsPDF, page: number, total: number) {
  doc.setDrawColor(...RULE);
  doc.setLineWidth(0.3);
  doc.line(MARGIN, PAGE_H - 14, PAGE_W - MARGIN, PAGE_H - 14);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text("Grounded evidence only. Missing values are left blank.", MARGIN, PAGE_H - 8);
  doc.text(`${page} / ${total}`, PAGE_W - MARGIN, PAGE_H - 8, { align: "right" });
}

export function renderActionPlanPdf(plan: ActionPlanDocument): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  let y = 0;

  const ensure = (needed: number) => {
    if (y + needed < PAGE_H - 18) return;
    doc.addPage();
    y = 20;
  };

  const section = (title: string) => {
    ensure(16);
    y += 4;
    doc.setFillColor(...FOREST);
    doc.rect(MARGIN, y, 2.2, 6.2, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.setTextColor(...FOREST);
    doc.text(title, MARGIN + 6, y + 5);
    y += 12;
  };

  const body = (text: string, width = CONTENT_W) => {
    const lines = wrap(doc, stripMarkdownTables(text), width);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.setTextColor(...INK);
    for (const line of lines) {
      ensure(6);
      doc.text(line, MARGIN, y);
      y += 5;
    }
  };

  const muted = (text: string) => {
    const lines = wrap(doc, text);
    doc.setFont("helvetica", "italic");
    doc.setFontSize(9);
    doc.setTextColor(...MUTED);
    for (const line of lines) {
      ensure(5.5);
      doc.text(line, MARGIN, y);
      y += 4.8;
    }
  };

  const checkbox = (label: string, extra?: string) => {
    const lines = wrap(doc, label, CONTENT_W - 8);
    ensure(8 + (extra ? 8 : 0) + lines.length * 4.6);
    doc.setDrawColor(...FOREST);
    doc.setLineWidth(0.35);
    doc.rect(MARGIN, y - 3.1, 3.4, 3.4);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.setTextColor(...INK);
    lines.forEach((line, index) => {
      doc.text(line, MARGIN + 7, y + index * 4.8);
    });
    y += Math.max(7, lines.length * 4.8 + 2);
    if (extra) {
      const more = wrap(doc, extra, CONTENT_W - 8);
      doc.setFontSize(9);
      doc.setTextColor(...MUTED);
      more.forEach((line) => {
        ensure(5);
        doc.text(line, MARGIN + 7, y);
        y += 4.6;
      });
      y += 1.5;
    }
  };

  const table = (data: MarkdownTable) => {
    const colCount = Math.max(1, data.headers.length);
    const colW = CONTENT_W / colCount;
    const pad = 1.5;
    const lineH = 3.7;
    const fontSize = colCount >= 5 ? 7.2 : 8.2;

    const cellLines = (text: string) => {
      doc.setFontSize(fontSize);
      return wrap(doc, (text || "").replace(/\|/g, "/"), colW - pad * 2);
    };
    const rowHeight = (cells: string[]) => {
      const maxLines = Math.max(1, ...cells.map((cell) => cellLines(cell).length));
      return Math.min(PAGE_H - 40, Math.max(7.5, maxLines * lineH + pad * 2));
    };
    const drawRow = (cells: string[], header: boolean) => {
      const height = rowHeight(cells);
      ensure(height + 1);
      if (header) {
        doc.setFillColor(...FOREST);
        doc.setTextColor(252, 249, 243);
        doc.setFont("helvetica", "bold");
      } else {
        doc.setFillColor(252, 249, 243);
        doc.setTextColor(...INK);
        doc.setFont("helvetica", "normal");
      }
      doc.rect(MARGIN, y, CONTENT_W, height, "F");
      doc.setDrawColor(...RULE);
      doc.setLineWidth(0.2);
      doc.rect(MARGIN, y, CONTENT_W, height);
      cells.forEach((cell, index) => {
        const x = MARGIN + index * colW;
        if (index > 0) doc.line(x, y, x, y + height);
        doc.setFontSize(fontSize);
        if (header) {
          doc.setFont("helvetica", "bold");
          doc.setTextColor(252, 249, 243);
        } else {
          doc.setFont("helvetica", "normal");
          doc.setTextColor(...INK);
        }
        cellLines(cell).forEach((line, lineIndex) => {
          doc.text(line, x + pad, y + pad + 3.1 + lineIndex * lineH);
        });
      });
      y += height;
    };

    drawRow(data.headers, true);
    data.rows.forEach((row) => {
      drawRow(
        data.headers.map((_, index) => row[index] || ""),
        false,
      );
    });
    y += 3;
  };

  doc.setFillColor(...FOREST);
  doc.rect(0, 0, PAGE_W, 36, "F");
  doc.setFillColor(...ACCENT);
  doc.rect(0, 36, PAGE_W, 1.4, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.setTextColor(252, 249, 243);
  doc.text(plan.heading, MARGIN, 18);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.text(plan.generatedLabel, MARGIN, 27);
  y = 46;

  section("1. Site Profile");
  if (!plan.siteProfile.length) {
    muted("No land details were provided for this response.");
  } else {
    for (const row of plan.siteProfile) {
      ensure(7);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      doc.setTextColor(...FOREST);
      doc.text(row.label, MARGIN, y);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...INK);
      const valueLines = wrap(doc, row.value, CONTENT_W - 52);
      doc.text(valueLines[0] || "", MARGIN + 52, y);
      y += 5.2;
      for (const extra of valueLines.slice(1)) {
        ensure(5.2);
        doc.text(extra, MARGIN + 52, y);
        y += 5.2;
      }
    }
  }

  section("2. Assessment Summary");
  if (plan.assessment) body(plan.assessment);
  else muted("No grounded assessment text was returned.");

  if (plan.investigateFirst) {
    section("3. What to investigate first");
    body(plan.investigateFirst);
  }

  section(plan.investigateFirst ? "4. Recommendations" : "3. Recommendations");
  if (plan.recommendationTable && plan.recommendationTable.rows.length) {
    table(plan.recommendationTable);
  } else {
    muted("No recommendations were returned for this response.");
  }

  if (plan.whyTogether) {
    section("Why these work together");
    body(plan.whyTogether);
  }
  if (plan.nextSteps) {
    section("Next steps");
    body(plan.nextSteps);
  }

  section("Monitoring Checklist");
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

  section("Sources / Evidence");
  if (!plan.kbSources.length && !plan.externalSources.length) {
    muted("No supporting sources were used in the grounded response.");
  }
  if (plan.kbSources.length) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(...FOREST);
    ensure(6);
    doc.text("Internal knowledge base", MARGIN, y);
    y += 6;
    for (const source of plan.kbSources) {
      body(`${source.title} — ${source.evidenceLevel}${source.link ? `. ${source.link}` : ""}`);
    }
  }
  if (plan.externalSources.length) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(...FOREST);
    ensure(6);
    doc.text("External scientific sources", MARGIN, y);
    y += 6;
    for (const source of plan.externalSources) {
      body(`${source.title} — ${source.evidenceLevel}${source.link ? `. ${source.link}` : ""}`);
    }
  } else {
    muted("No external scientific sources were used.");
  }

  section("Uncertainty");
  if (!plan.limitations.length) muted("No additional uncertainty statement was returned.");
  else plan.limitations.forEach((line) => body(line));

  const total = doc.getNumberOfPages();
  for (let page = 1; page <= total; page += 1) {
    doc.setPage(page);
    if (page > 1) {
      doc.setDrawColor(...FOREST);
    }
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
