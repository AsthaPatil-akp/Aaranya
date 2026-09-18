import { jsPDF } from "jspdf";
import { buildActionPlan, ActionPlanDocument } from "./actionPlan";
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
    const lines = wrap(doc, text, width);
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

  section("3. Recommended Actions");
  if (!plan.recommendations.length) {
    muted("No recommendations were returned for this response.");
  } else {
    plan.recommendations.forEach((item, index) => {
      checkbox(`${index + 1}. ${item.action}`);
      body(`Why it may help: ${item.why || "The retrieved evidence does not support a more specific explanation."}`);
      if (item.metrics.length) {
        const metricText = item.metrics
          .map((metric) => `${metric.name}: ${metric.note || "potentially affected"}`)
          .join("; ");
        body(`Impacted metrics: ${metricText}`);
      } else {
        muted("Impacted metrics: not returned for this recommendation.");
      }
      body(
        `Time horizon: ${item.timeHorizon || "No specific timeframe is supported by the retrieved evidence."}`,
      );
      if (item.sources.length) body(`Supporting evidence: ${item.sources.join("; ")}`);
      else muted("Supporting evidence: no titles were returned for this recommendation.");
      y += 2;
    });
  }

  section("4. Monitoring Checklist");
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

  section("5. Scientific Evidence");
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

  section("6. Limitations / Uncertainty");
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
