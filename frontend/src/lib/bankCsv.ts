const COLUMN_ALIASES: Record<string, string[]> = {
  word: ["word", "vocabulary", "term", "english"],
  level: ["level", "cefr", "cefr_level", "grade", "difficulty"],
  category: ["categories", "category", "topic", "theme", "tag", "subject"],
  definition: ["definition", "meaning", "def", "translation"],
};

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const LEVEL_MAX_LENGTH = 32;
const CATEGORY_MAX_LENGTH = 64;
const CATEGORY_SPLIT_RE = /\s+and\s+|\s*;\s*|\s*,\s*|\s+-\s+/i;

function parseCategories(value: string): string[] {
  const parts = value
    .split(CATEGORY_SPLIT_RE)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : ["General"];
}

export type BankCsvValidation = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  rowCount: number;
  detectedColumns: string[];
};

function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

function resolveColumnMap(headers: string[]): Record<string, string> {
  const lower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const map: Record<string, string> = {};
  for (const [canonical, aliases] of Object.entries(COLUMN_ALIASES)) {
    for (const alias of aliases) {
      if (lower.has(alias)) {
        map[canonical] = alias;
        break;
      }
    }
  }
  return map;
}

export async function validateBankCsvFile(file: File): Promise<BankCsvValidation> {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!file.name.toLowerCase().endsWith(".csv")) {
    errors.push("File must be a .csv");
  }
  if (file.size > MAX_FILE_BYTES) {
    errors.push("File is too large (max 5 MB)");
  }
  if (file.size === 0) {
    errors.push("File is empty");
    return { ok: false, errors, warnings, rowCount: 0, detectedColumns: [] };
  }

  const text = await file.text();
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) {
    errors.push("CSV must include a header row and at least one word row");
    return { ok: false, errors, warnings, rowCount: 0, detectedColumns: [] };
  }

  const headers = parseCsvLine(lines[0]).map((h) => h.trim().toLowerCase());
  const columnMap = resolveColumnMap(headers);
  const detectedColumns = Object.keys(columnMap);

  for (const required of ["word", "level", "category"] as const) {
    if (!(required in columnMap)) {
      errors.push(`Missing required column: ${required}`);
    }
  }

  const rowCount = lines.length - 1;
  if (rowCount > 10_000) {
    errors.push("CSV has too many rows (max 10,000)");
  }

  if (errors.length > 0) {
    return { ok: false, errors, warnings, rowCount, detectedColumns };
  }

  const headerIndex = Object.fromEntries(headers.map((h, i) => [h, i]));
  const levelIdx = headerIndex[columnMap.level];
  const categoryIdx = headerIndex[columnMap.category];
  let blankLevels = 0;
  let longLevels = 0;
  let longCategories = 0;

  for (let i = 1; i < Math.min(lines.length, 51); i += 1) {
    const cells = parseCsvLine(lines[i]);
    const level = (cells[levelIdx] ?? "").trim();
    const categoryCell = (cells[categoryIdx] ?? "").trim();
    const categories = categoryCell ? parseCategories(categoryCell) : [];
    if (!level) {
      blankLevels += 1;
    } else if (level.length > LEVEL_MAX_LENGTH) {
      longLevels += 1;
    }
    if (categories.some((category) => category.length > CATEGORY_MAX_LENGTH)) {
      longCategories += 1;
    }
  }

  if (blankLevels > 0) {
    warnings.push(`${blankLevels}+ row(s) in preview are missing a level`);
  }
  if (longLevels > 0) {
    warnings.push(`${longLevels}+ row(s) in preview have levels longer than ${LEVEL_MAX_LENGTH} characters`);
  }
  if (longCategories > 0) {
    warnings.push(
      `${longCategories}+ row(s) in preview have categories that are too long after splitting on "and"`,
    );
  }

  return { ok: true, errors, warnings, rowCount, detectedColumns };
}
