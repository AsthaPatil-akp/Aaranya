import { parseMarkdownTables, stripMarkdownTables, hideInternalEvidenceIds, MarkdownTable } from "./markdown";

export type PdfListItem = {
  title: string;
  body: string;
};

export type PdfBlock =
  | { type: "paragraph"; text: string }
  | { type: "heading"; text: string }
  | { type: "ordered-list"; items: PdfListItem[] }
  | { type: "unordered-list"; items: string[] };

const DUPLICATE_HEADING =
  /^(assessment summary|what to investigate first|recommendations?|recommended actions?|why these work together|next steps?|sources\s*\/?\s*evidence|uncertainty|monitoring checklist|limitations?)$/i;

export function normalizePdfText(text: string): string {
  return String(text || "")
    .replace(/\u00a0/g, " ")
    .replace(/[\u2000-\u200A\u202F\u205F\u3000]/g, " ")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/°/g, " deg")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[–—]/g, "-")
    .replace(/\r\n/g, "\n");
}

/**
 * Break ATX headings that appear after other text on the same line.
 * Requires whitespace before the hashes and a space after them so URL fragments
 * (`example.com/path#section`) and tokens like `C#` are left alone.
 */
export function splitInlineAtxHeadings(text: string): string {
  return String(text || "").replace(
    /([^\s#])([ \t]+)(#{1,6})[ \t]+(?=[^\s#])/g,
    "$1\n\n$3 ",
  );
}

export function stripMarkdownSyntax(text: string): string {
  return normalizePdfText(text)
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .replace(/(^|[^*])\*(?!\s)([^*]+?)\*(?!\*)/g, "$1$2")
    .replace(/^[ \t]*[-*][ \t]+/gm, "")
    .replace(/^[ \t]*\d+[.)]\s+/gm, "")
    .replace(/\|/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function isDuplicateHeadingLine(line: string): boolean {
  const stripped = line
    .replace(/^\s{0,3}#{1,6}\s+/, "")
    .replace(/\*+/g, "")
    .replace(/[:.]+$/, "")
    .trim();
  return Boolean(stripped) && stripped.length <= 80 && DUPLICATE_HEADING.test(stripped);
}

function splitListMarker(line: string): { ordered: boolean; rest: string } | null {
  const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
  if (ordered) return { ordered: true, rest: ordered[1] };
  const bullet = line.match(/^\s*[-*]\s+(.*)$/);
  if (bullet) return { ordered: false, rest: bullet[1] };
  return null;
}

function splitTitleBody(raw: string): PdfListItem {
  const cleaned = stripMarkdownSyntax(raw);
  const dash = cleaned.match(/^(.+?)\s*[-:]\s+(.+)$/);
  if (dash && dash[1].length <= 80) {
    return { title: dash[1].trim(), body: dash[2].trim() };
  }
  const sentence = cleaned.match(/^(.{8,90}[.!?])\s+(.+)$/);
  if (sentence) {
    return { title: sentence[1].trim(), body: sentence[2].trim() };
  }
  return { title: cleaned, body: "" };
}

function flushParagraph(buffer: string[], blocks: PdfBlock[]) {
  const text = stripMarkdownSyntax(buffer.join(" ").replace(/\s+/g, " "));
  buffer.length = 0;
  if (text) blocks.push({ type: "paragraph", text });
}

function splitRunOnOrdered(text: string): string[] {
  const source = text.trim();
  if (!/^\d+[.)]\s/.test(source) || !/\s+\d+[.)]\s/.test(source)) return [source];
  return source
    .split(/(?=\d+[.)]\s)/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function parsePdfBlocks(markdown: string): PdfBlock[] {
  const withoutTables = stripMarkdownTables(
    splitInlineAtxHeadings(normalizePdfText(hideInternalEvidenceIds(markdown || ""))),
  );
  const lines = withoutTables.split("\n");
  const blocks: PdfBlock[] = [];
  let paragraph: string[] = [];
  let ordered: PdfListItem[] = [];
  let bullets: string[] = [];
  let previousBlank = false;

  const flushLists = () => {
    if (ordered.length) {
      blocks.push({ type: "ordered-list", items: ordered });
      ordered = [];
    }
    if (bullets.length) {
      blocks.push({ type: "unordered-list", items: bullets });
      bullets = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushParagraph(paragraph, blocks);
      previousBlank = true;
      continue;
    }
    const atx = line.match(/^(#{1,6})\s+(.+)$/);
    if (atx) {
      flushParagraph(paragraph, blocks);
      flushLists();
      previousBlank = false;
      const headingText = stripMarkdownSyntax(atx[2]);
      if (headingText) blocks.push({ type: "heading", text: headingText });
      continue;
    }
    if (isDuplicateHeadingLine(line)) {
      flushParagraph(paragraph, blocks);
      flushLists();
      previousBlank = false;
      continue;
    }

    const runOn = splitRunOnOrdered(line);
    if (runOn.length > 1) {
      flushParagraph(paragraph, blocks);
      flushLists();
      blocks.push({
        type: "ordered-list",
        items: runOn.map((item) => splitTitleBody(item.replace(/^\d+[.)]\s+/, ""))),
      });
      previousBlank = false;
      continue;
    }

    const marker = splitListMarker(line);
    if (marker?.ordered) {
      flushParagraph(paragraph, blocks);
      if (bullets.length) {
        blocks.push({ type: "unordered-list", items: bullets });
        bullets = [];
      }
      ordered.push(splitTitleBody(marker.rest));
      previousBlank = false;
      continue;
    }
    if (marker && !marker.ordered) {
      flushParagraph(paragraph, blocks);
      if (ordered.length) {
        blocks.push({ type: "ordered-list", items: ordered });
        ordered = [];
      }
      bullets.push(stripMarkdownSyntax(marker.rest));
      previousBlank = false;
      continue;
    }
    if ((ordered.length || bullets.length) && !previousBlank) {
      const extra = stripMarkdownSyntax(line);
      if (ordered.length) {
        const last = ordered[ordered.length - 1];
        last.body = [last.body, extra].filter(Boolean).join(" ");
      } else {
        bullets[bullets.length - 1] = [bullets[bullets.length - 1], extra].filter(Boolean).join(" ");
      }
      continue;
    }
    flushLists();
    previousBlank = false;
    paragraph.push(line);
  }
  flushParagraph(paragraph, blocks);
  flushLists();
  return blocks;
}

const PDF_HEADERS = [
  "Intervention",
  "What to do",
  "Why it may help",
  "Potentially affected metrics",
  "Time horizon",
] as const;

function headerIndex(headers: string[], pattern: RegExp): number {
  return headers.findIndex((header) => pattern.test(header || ""));
}

export function normalizeRecommendationTable(
  table: MarkdownTable | null,
  fallbackRows: string[][],
): MarkdownTable {
  const source = table && table.rows.length ? table : { headers: [...PDF_HEADERS], rows: fallbackRows };
  const headers = source.headers.map((header) => stripMarkdownSyntax(header));
  const interventionAt = headerIndex(headers, /intervention/i);
  const whatAt = headerIndex(headers, /what to do|action(?!s)/i);
  const whyAt = headerIndex(headers, /why/i);
  const metricsAt = headerIndex(headers, /metric/i);
  const horizonAt = headerIndex(headers, /time|horizon/i);
  const rows = source.rows.map((row, index) => {
    const fallback = fallbackRows[index] || [];
    const cell = (at: number, fallbackIndex: number) =>
      stripMarkdownSyntax((at >= 0 ? row[at] : "") || fallback[fallbackIndex] || "");
    const intervention = cell(interventionAt, 0);
    const what = cell(whatAt >= 0 && whatAt !== interventionAt ? whatAt : -1, 1) || (whatAt === interventionAt ? "" : cell(0, 1));
    return [
      intervention || fallback[0] || what,
      what || intervention || fallback[1] || "",
      cell(whyAt, 2),
      cell(metricsAt, 3),
      cell(horizonAt, 4),
    ];
  });
  return { headers: [...PDF_HEADERS], rows };
}

export function markdownTablesFromSection(text: string): MarkdownTable[] {
  return parseMarkdownTables(text || "").map((table) => ({
    headers: table.headers.map((header) => stripMarkdownSyntax(header)),
    rows: table.rows.map((row) => row.map((cell) => stripMarkdownSyntax(cell))),
  }));
}
