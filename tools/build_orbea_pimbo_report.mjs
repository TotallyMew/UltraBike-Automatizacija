import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [checkpointPath, outputPath, previewDir] = process.argv.slice(2);
if (!checkpointPath || !outputPath || !previewDir) {
  throw new Error(
    "Usage: node build_orbea_pimbo_report.mjs <checkpoint.json> <output.xlsx> <preview-dir>",
  );
}

const artifactEntry =
  process.env.CODEX_ARTIFACT_TOOL_ENTRY ||
  path.join(
    os.homedir(),
    ".cache",
    "codex-runtimes",
    "codex-primary-runtime",
    "dependencies",
    "node",
    "node_modules",
    "@oai",
    "artifact-tool",
    "dist",
    "artifact_tool.mjs",
  );

try {
  await fs.access(artifactEntry);
} catch {
  throw new Error(
    `Artifact Tool was not found at ${artifactEntry}. ` +
      "Set CODEX_ARTIFACT_TOOL_ENTRY to artifact_tool.mjs.",
  );
}

const { SpreadsheetFile, Workbook } = await import(
  pathToFileURL(artifactEntry).href
);

const checkpoint = JSON.parse(await fs.readFile(checkpointPath, "utf8"));
const results = Array.isArray(checkpoint.results) ? checkpoint.results : [];
const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const matchesSheet = workbook.worksheets.add("Matches");
const reviewSheet = workbook.worksheets.add("Review");
const rawSheet = workbook.worksheets.add("Raw Scan");

const COLORS = {
  navy: "#17324D",
  blue: "#2E75B6",
  paleBlue: "#DCEAF7",
  green: "#2E7D32",
  paleGreen: "#E2F0D9",
  amber: "#B26A00",
  paleAmber: "#FFF2CC",
  red: "#B42318",
  paleRed: "#FCE8E6",
  grey: "#5F6B76",
  paleGrey: "#EEF1F4",
  white: "#FFFFFF",
  border: "#D9E1E8",
};

const statusLabels = {
  code_match: "Code match",
  title_only: "Title only — review",
  ambiguous: "Ambiguous — review",
  unmatched: "Unmatched",
  no_variant: "No variant SKU",
  error: "Browser error",
  duplicate: "Duplicate product",
  excluded: "Excluded",
};

function asDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const rawHeaders = [
  "Page",
  "Row",
  "Pimbo Product",
  "List Code",
  "Variant SKU",
  "Variant Stock",
  "Product URL",
  "Result",
  "Match Method",
  "Catalogue Code",
  "Catalogue Model",
  "Year",
  "Category",
  "Subcategory",
  "Orbea URL",
  "Candidate Reason",
  "Notes",
  "Scanned At",
];

const rawRows = results.map((item) => [
  item.page ?? null,
  item.row ?? null,
  item.title ?? "",
  item.visible_code ?? "",
  item.sku ?? "",
  item.variant_stock ?? null,
  item.product_url ?? "",
  statusLabels[item.status] || item.status || "",
  item.match_method ?? "",
  item.catalogue_code ?? "",
  item.catalogue_model ?? "",
  item.catalogue_year ?? null,
  item.catalogue_category ?? "",
  item.catalogue_subcategory ?? "",
  item.catalogue_url ?? "",
  item.candidate_reason ?? "",
  item.note ?? "",
  asDate(item.scanned_at),
]);

function setHeaderStyle(range) {
  range.format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  range.format.rowHeight = 30;
}

function configureDataSheet(sheet, headers, rows, widths, tableName) {
  sheet.showGridLines = false;
  const matrix = [headers, ...rows];
  sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).values = matrix;
  setHeaderStyle(sheet.getRangeByIndexes(0, 0, 1, headers.length));
  sheet.freezePanes.freezeRows(1);
  sheet.getRangeByIndexes(1, 0, Math.max(rows.length, 1), headers.length).format = {
    verticalAlignment: "top",
    borders: {
      insideHorizontal: { style: "thin", color: COLORS.border },
    },
  };
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, Math.max(matrix.length, 1), 1).format.columnWidth =
      width;
  });
  if (rows.length > 0) {
    const table = sheet.tables.add(
      sheet.getRangeByIndexes(0, 0, matrix.length, headers.length),
      true,
      tableName,
    );
    table.style = "TableStyleMedium2";
    table.showFilterButton = true;
  }
}

configureDataSheet(
  rawSheet,
  rawHeaders,
  rawRows,
  [8, 7, 48, 18, 16, 13, 42, 21, 22, 17, 30, 9, 16, 20, 42, 22, 42, 23],
  "RawScanTable",
);
rawSheet.getRange(`C2:C${Math.max(rawRows.length + 1, 2)}`).format.wrapText = true;
rawSheet.getRange(`Q2:Q${Math.max(rawRows.length + 1, 2)}`).format.wrapText = true;
rawSheet.getRange(`R2:R${Math.max(rawRows.length + 1, 2)}`).format.numberFormat =
  "yyyy-mm-dd hh:mm";

const rawLastRow = Math.max(rawRows.length + 1, 2);
const resultRange = rawSheet.getRange(`H2:H${rawLastRow}`);
for (const [text, fill, font] of [
  ["Code match", COLORS.paleGreen, COLORS.green],
  ["Title only — review", COLORS.paleAmber, COLORS.amber],
  ["Ambiguous — review", COLORS.paleAmber, COLORS.amber],
  ["Unmatched", COLORS.paleRed, COLORS.red],
  ["No variant SKU", COLORS.paleRed, COLORS.red],
  ["Browser error", COLORS.paleRed, COLORS.red],
  ["Excluded", COLORS.paleGrey, COLORS.grey],
]) {
  resultRange.conditionalFormats.add("containsText", {
    text,
    format: { fill, font: { color: font, bold: text === "Code match" } },
  });
}

const matchHeaders = [
  "Variant SKU",
  "Pimbo Product",
  "Stock",
  "Catalogue Code",
  "Catalogue Model",
  "Year",
  "Category",
  "Subcategory",
  "Match Method",
  "Pimbo URL",
  "Orbea URL",
  "Page",
];
const matchedResults = results.filter((item) => item.status === "code_match");
const matchRows = matchedResults.map((item) => [
  item.sku ?? "",
  item.title ?? "",
  item.variant_stock ?? null,
  item.catalogue_code ?? "",
  item.catalogue_model ?? "",
  item.catalogue_year ?? null,
  item.catalogue_category ?? "",
  item.catalogue_subcategory ?? "",
  item.match_method ?? "",
  item.product_url ?? "",
  item.catalogue_url ?? "",
  item.page ?? null,
]);
configureDataSheet(
  matchesSheet,
  matchHeaders,
  matchRows,
  [16, 48, 11, 17, 30, 9, 16, 20, 24, 42, 42, 8],
  "MatchesTable",
);
matchesSheet.getRange(`B2:B${Math.max(matchRows.length + 1, 2)}`).format.wrapText = true;

const reviewStatuses = new Set([
  "title_only",
  "ambiguous",
  "unmatched",
  "no_variant",
  "error",
]);
const reviewHeaders = [
  "Result",
  "Variant SKU",
  "Pimbo Product",
  "List Code",
  "Suggested Catalogue Code",
  "Suggested Model",
  "Reason",
  "Pimbo URL",
  "Page",
];
const reviewResults = results.filter((item) => reviewStatuses.has(item.status));
const reviewRows = reviewResults.map((item) => [
  statusLabels[item.status] || item.status || "",
  item.sku ?? "",
  item.title ?? "",
  item.visible_code ?? "",
  item.catalogue_code ?? "",
  item.catalogue_model ?? "",
  item.note ?? "",
  item.product_url ?? "",
  item.page ?? null,
]);
configureDataSheet(
  reviewSheet,
  reviewHeaders,
  reviewRows,
  [22, 16, 48, 18, 23, 30, 46, 42, 8],
  "ReviewTable",
);
reviewSheet.getRange(`C2:C${Math.max(reviewRows.length + 1, 2)}`).format.wrapText = true;
reviewSheet.getRange(`G2:G${Math.max(reviewRows.length + 1, 2)}`).format.wrapText = true;

summary.showGridLines = false;
summary.getRange("A1:F1").merge();
summary.getRange("A1").values = [["Orbea ↔ Pimbo variant reconciliation"]];
summary.getRange("A1:F1").format = {
  fill: COLORS.navy,
  font: { bold: true, color: COLORS.white, size: 18 },
  verticalAlignment: "center",
};
summary.getRange("A1:F1").format.rowHeight = 38;
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [[
  "One actual in-stock variant SKU per likely bicycle; accessories remain visible in Raw Scan.",
]];
summary.getRange("A2:F2").format = {
  fill: COLORS.paleBlue,
  font: { color: COLORS.navy, italic: true },
  wrapText: true,
};
summary.getRange("A4:B4").values = [["Run details", "Value"]];
setHeaderStyle(summary.getRange("A4:B4"));
summary.getRange("A5:B9").values = [
  ["Search", checkpoint.filters?.search ?? "orbea"],
  ["Status", checkpoint.filters?.status ?? "Draft"],
  ["Stock", checkpoint.filters?.stock ?? "In stock"],
  ["Updated", asDate(checkpoint.updated_at)],
  ["Run state", checkpoint.completed ? "Complete" : "Partial / resumable"],
];
summary.getRange("B8").format.numberFormat = "yyyy-mm-dd hh:mm";

summary.getRange("D4:E4").values = [["Results", "Count"]];
setHeaderStyle(summary.getRange("D4:E4"));
summary.getRange("D5:D13").values = [
  ["Filtered products"],
  ["Rows scanned"],
  ["Candidate products opened"],
  ["Code matches"],
  ["Title-only review"],
  ["Ambiguous review"],
  ["Unmatched"],
  ["No variant / browser error"],
  ["Excluded accessories/components"],
];
summary.getRange("E5").values = [[checkpoint.total_products ?? null]];
summary.getRange("E6").formulas = [[`=COUNTA('Raw Scan'!A2:A${rawLastRow})`]];
summary.getRange("E7").formulas = [[
  `=E6-COUNTIF('Raw Scan'!H2:H${rawLastRow},"Excluded")`,
]];
summary.getRange("E8").formulas = [[
  `=COUNTIF('Raw Scan'!H2:H${rawLastRow},"Code match")`,
]];
summary.getRange("E9").formulas = [[
  `=COUNTIF('Raw Scan'!H2:H${rawLastRow},"Title only — review")`,
]];
summary.getRange("E10").formulas = [[
  `=COUNTIF('Raw Scan'!H2:H${rawLastRow},"Ambiguous — review")`,
]];
summary.getRange("E11").formulas = [[
  `=COUNTIF('Raw Scan'!H2:H${rawLastRow},"Unmatched")`,
]];
summary.getRange("E12").formulas = [[
  `=COUNTIF('Raw Scan'!H2:H${rawLastRow},"No variant SKU")+COUNTIF('Raw Scan'!H2:H${rawLastRow},"Browser error")`,
]];
summary.getRange("E13").formulas = [[
  `=COUNTIF('Raw Scan'!H2:H${rawLastRow},"Excluded")`,
]];
summary.getRange("D15:E15").values = [["Scan progress", null]];
setHeaderStyle(summary.getRange("D15:E15"));
summary.getRange("E15").formulas = [[
  checkpoint.total_products
    ? `=IFERROR(E6/E5,0)`
    : "=0",
]];
summary.getRange("E15").format.numberFormat = "0.0%";
summary.getRange("A11:B14").values = [
  ["How codes link", "Catalogue U107TTCC matches Pimbo U10707SV by the U107 prefix."],
  ["Duplicate locales", "Catalogue rows are collapsed to one logical code/model before matching."],
  ["Safe stopping", "Ctrl+C keeps the checkpoint and creates a partial report."],
  ["Review rule", "Title-only suggestions are never counted as confirmed code matches."],
];
summary.getRange("A11:B14").format = {
  fill: COLORS.paleGrey,
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "all", style: "thin", color: COLORS.border },
};
summary.getRange("A5:B9").format.borders = {
  preset: "all",
  style: "thin",
  color: COLORS.border,
};
summary.getRange("D5:E15").format.borders = {
  preset: "all",
  style: "thin",
  color: COLORS.border,
};
summary.getRange("A1:A15").format.columnWidth = 24;
summary.getRange("B1:B15").format.columnWidth = 58;
summary.getRange("C1:C15").format.columnWidth = 4;
summary.getRange("D1:D15").format.columnWidth = 30;
summary.getRange("E1:E15").format.columnWidth = 16;
summary.getRange("F1:F15").format.columnWidth = 4;
summary.freezePanes.freezeRows(2);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const inspection = await workbook.inspect({
  kind: "workbook,sheet,table,formula",
  maxChars: 12000,
  tableMaxRows: 5,
  tableMaxCols: 18,
  tableMaxCellChars: 100,
});
await fs.writeFile(
  path.join(previewDir, "inspection.ndjson"),
  inspection.ndjson ?? JSON.stringify(inspection),
  "utf8",
);

for (const [sheetName, range, fileName, scale] of [
  ["Summary", "A1:F15", "summary.png", 1],
  ["Matches", `A1:L${Math.min(Math.max(matchRows.length + 1, 2), 20)}`, "matches.png", 0.9],
  ["Review", `A1:I${Math.min(Math.max(reviewRows.length + 1, 2), 20)}`, "review.png", 0.9],
]) {
  const preview = await workbook.render({
    sheetName,
    range,
    autoCrop: "all",
    scale,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, fileName),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
try {
  await fs.rename(
    `${outputPath}.inspect.ndjson`,
    path.join(previewDir, "export-inspection.ndjson"),
  );
} catch {
  // Some Artifact Tool builds do not emit the additional export inspection.
}
console.log(
  `Built ${outputPath} (${matchRows.length} matches, ${reviewRows.length} review rows, ${rawRows.length} scanned rows).`,
);
