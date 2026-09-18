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

const INTERNAL_ID = /\[?\b(?:kb|oa)[-:]?\s*\d+\b\]?/gi;

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
  return text.replace(INTERNAL_ID, (raw) => {
    const key = raw.replace(/[[\]\s]/g, "").toLowerCase().replace(":", "-");
    const compact = key.replace(/-/g, "");
    return titlesById[key] || titlesById[compact] || "";
  });
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
