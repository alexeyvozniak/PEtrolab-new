import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("..", import.meta.url);
const read = (path) => readFile(new URL(path, root), "utf8");

test("raw import preview can navigate beyond the initial bounded window", async () => {
  const review = await read("src/ImportBlockReview.jsx");
  const api = await read("src/desktopApi.js");

  assert.match(review, /previewImportWindow/);
  assert.match(review, /PREVIEW_ROW_COUNT = 30/);
  assert.match(review, /К строке/);
  assert.match(review, /К заголовку/);
  assert.match(review, /← Выше/);
  assert.match(review, /Ниже →/);
  assert.match(review, /used_range/);
  assert.match(review, /setPreviewTarget/);
  assert.match(review, /window\.setTimeout/);
  assert.match(review, /Читаю другой участок листа/);

  assert.match(api, /source_path: sourcePath/);
  assert.match(api, /result: \{ \.\.\.response\.result, source_path: sourcePath \}/);
});

test("preview navigation does not apply or mutate an import recipe", async () => {
  const review = await read("src/ImportBlockReview.jsx");
  const rawPreview = review.match(/function RawPreview\([\s\S]*?\n}\n\nfunction BlockCard/)?.[0] ?? "";
  assert.doesNotMatch(rawPreview, /onApply|reviseImportSections|reviseImportMappings/);
  assert.match(rawPreview, /onNavigate/);
});
