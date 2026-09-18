export type MarkdownTable = {
  headers: string[];
  rows: string[][];
};

export type AnswerSections = {
  assessment_summary: string;
  investigate_first: string;
  recommendations: string;
  why_together: string;
  next_steps: string;
  sources: string;
  uncertainty: string;
};

const INTERNAL_ID = /\[?\b(?:kb|oa)[-:]?\s*[A-Za-z]*\d+[A-Za-z0-9]*\b\]?/gi;
const LEFTOVER_INTERNAL_ID = /\[?\b(?:kb|oa)[-:][A-Za-z0-9]+\b\]?/gi;
const ACTION_PLAN_TITLES = [
  "Assessment Summary",
  "What to investigate first",
  "Recommendations",
  "Why these work together",
  "Next steps",
  "Sources / Evidence",
  "Uncertainty",
];

const HEADING_ALIASES: Array<[keyof AnswerSections, RegExp]> = [
  ["assessment_summary", /^assessment summary$/i],
  ["investigate_first", /^what to investigate first$/i],
  ["investigate_first", /^what i would investigate first(?:, based on the retrieved evidence)?$/i],
  ["investigate_first", /^investigate first$/i],
  ["recommendations", /^recommendations?$/i],
  ["recommendations", /^recommended actions?$/i],
  ["why_together", /^why these work together$/i],
  ["why_together", /^why (?:it|they)(?: may)? work(?: together)?$/i],
  ["next_steps", /^next steps?$/i],
  ["sources", /^sources(?:\s*\/\s*evidence)?$/i],
  ["sources", /^references$/i],
  ["sources", /^internal knowledge base$/i],
  ["sources", /^external scientific (?:research|sources)$/i],
  ["uncertainty", /^uncertainty$/i],
  ["uncertainty", /^limitations?(?:\s*\/\s*uncertainty)?$/i],
];

export function hideInternalEvidenceIds(text: string, titlesById: Record<string, string> = {}): string {
  if (!text) return "";
  const cleaned = text.replace(INTERNAL_ID, (raw) => {
    const key = raw.replace(/[[\]\s]/g, "").toLowerCase().replace(":", "-");
    const compact = key.replace(/-/g, "");
    return titlesById[key] || titlesById[compact] || "";
  });
  return cleaned.replace(LEFTOVER_INTERNAL_ID, "");
}

export function normalizeChatMarkdown(text: string): string {
  let value = String(text || "").replace(/\r\n/g, "\n");
  if (!value.includes("\n") && /\\n/.test(value)) {
    value = value.replace(/\\n/g, "\n");
  }
  value = value.replace(/([^\s#])([ \t]+)(#{1,6})[ \t]+(?=[^\s#])/g, "$1\n\n$3 ");
  value = value.replace(/([^\s#])(#{1,6}[ \t]+)(?=[^\s#])/g, "$1\n\n$2");
  for (const title of ACTION_PLAN_TITLES) {
    const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    value = value.replace(new RegExp(`(#{1,6}\\s*${escaped})(?=\\S)`, "gi"), "$1\n\n");
    value = value.replace(new RegExp(`(#{1,6}\\s*${escaped})[ \\t]+(?=[A-Z0-9*\\-])`, "gi"), "$1\n\n");
    value = value.replace(new RegExp(`(?<!#)(\\b${escaped})(?=[A-Z])`, "g"), "$1\n\n");
  }
  value = value.replace(
    /^(#{1,6}\s+(?:what(?:['’]s|s)?\s+(?:is|are)|what(?:['’]s|s))\b[^\n]{0,70}\?)[ \t]+(?=[A-Z])/gim,
    "$1\n\n",
  );
  value = value
    .split("\n")
    .map((line) => {
      if (isTableRow(line) || isSeparator(line)) return line;
      return line
        .replace(/(?<=[.!?;:])\s+(?=\d{1,2}[.)]\s+\S)/g, "\n\n")
        .replace(/(?<=\S)\s+(?=[-*]\s+\*\*)/g, "\n\n")
        .replace(/(?<=\S)\s+(?=[-*]\s+[A-Z])/g, "\n\n");
    })
    .join("\n");
  const seen = new Set<string>();
  value = value
    .split("\n")
    .filter((line) => {
      if (!headingKey(line)) return true;
      const stripped = line
        .replace(/^#{1,6}\s*/, "")
        .replace(/\*+/g, "")
        .trim()
        .replace(/[:.]+$/, "")
        .trim()
        .toLowerCase();
      if (seen.has(stripped)) return false;
      seen.add(stripped);
      return true;
    })
    .join("\n");
  return value.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.includes("|", 1);
}

function isSeparator(line: string): boolean {
  const trimmed = line.trim();
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(trimmed);
}

function splitRow(line: string): string[] {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map((cell) => cell.trim().replace(/\\\|/g, "|"));
}

export function parseMarkdownTables(text: string): MarkdownTable[] {
  const lines = (text || "").split(/\r?\n/);
  const tables: MarkdownTable[] = [];
  let index = 0;
  while (index < lines.length) {
    if (isTableRow(lines[index]) && index + 1 < lines.length && isSeparator(lines[index + 1])) {
      const headers = splitRow(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && isTableRow(lines[index]) && !isSeparator(lines[index])) {
        const cells = splitRow(lines[index]);
        rows.push(headers.map((_, cellIndex) => cells[cellIndex] || ""));
        index += 1;
      }
      if (headers.length) tables.push({ headers, rows });
      continue;
    }
    index += 1;
  }
  return tables;
}

function headingKey(line: string): keyof AnswerSections | null {
  const stripped = line
    .replace(/^#{1,6}\s*/, "")
    .replace(/\*+/g, "")
    .trim()
    .replace(/[:.]+$/, "")
    .trim();
  if (!stripped || stripped.length > 80) return null;
  for (const [key, pattern] of HEADING_ALIASES) {
    if (pattern.test(stripped)) return key;
  }
  return null;
}

export function extractAnswerSections(text: string): AnswerSections {
  const empty: AnswerSections = {
    assessment_summary: "",
    investigate_first: "",
    recommendations: "",
    why_together: "",
    next_steps: "",
    sources: "",
    uncertainty: "",
  };
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const buckets: Record<keyof AnswerSections, string[]> = {
    assessment_summary: [],
    investigate_first: [],
    recommendations: [],
    why_together: [],
    next_steps: [],
    sources: [],
    uncertainty: [],
  };
  let current: keyof AnswerSections = "assessment_summary";
  for (const line of lines) {
    const key = headingKey(line);
    if (key) {
      current = key;
      continue;
    }
    buckets[current].push(line);
  }
  const unheadedTable = parseMarkdownTables(buckets.assessment_summary.join("\n"))[0];
  if (unheadedTable && !buckets.recommendations.join("\n").trim()) {
    const assessmentLines = buckets.assessment_summary;
    const tableStart = assessmentLines.findIndex(
      (line, index) => isTableRow(line) && isSeparator(assessmentLines[index + 1] || ""),
    );
    if (tableStart >= 0) {
      let tableEnd = tableStart + 2;
      while (
        tableEnd < assessmentLines.length &&
        isTableRow(assessmentLines[tableEnd]) &&
        !isSeparator(assessmentLines[tableEnd])
      ) {
        tableEnd += 1;
      }
      buckets.recommendations = assessmentLines.slice(tableStart, tableEnd);
      buckets.assessment_summary = [...assessmentLines.slice(0, tableStart), ...assessmentLines.slice(tableEnd)];
    }
  }
  (Object.keys(buckets) as (keyof AnswerSections)[]).forEach((key) => {
    empty[key] = buckets[key].join("\n").trim();
  });
  return empty;
}

export function stripMarkdownTables(text: string): string {
  const lines = (text || "").split(/\r?\n/);
  const kept: string[] = [];
  let index = 0;
  while (index < lines.length) {
    if (isTableRow(lines[index]) && isSeparator(lines[index + 1] || "")) {
      index += 2;
      while (index < lines.length && isTableRow(lines[index]) && !isSeparator(lines[index])) {
        index += 1;
      }
      continue;
    }
    kept.push(lines[index]);
    index += 1;
  }
  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function markdownTableToString(table: MarkdownTable): string {
  const cell = (value: string) => (value || "").replace(/\|/g, "/").replace(/\s+/g, " ").trim();
  const header = `| ${table.headers.map(cell).join(" | ")} |`;
  const rule = `| ${table.headers.map(() => "---").join(" | ")} |`;
  const rows = table.rows.map((row) => `| ${table.headers.map((_, index) => cell(row[index] || "")).join(" | ")} |`);
  return [header, rule, ...rows].join("\n");
}
