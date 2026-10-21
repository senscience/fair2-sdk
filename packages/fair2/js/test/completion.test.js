// Completion of the query box, without a browser: `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { CompletionContext } from "@codemirror/autocomplete";
import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { DuckDB, columnCompletion, identifier, namespace } from "../src/query_box.js";

const SCHEMA = {
  task_results: ["task", "participant", "duration_ms"],
  "bloom/stroop.csv": ["identificacion", "duracion total (ms)", "Correctas"],
};

// The completion options at the end of `doc`, from every source, as {label: applied text}.
function complete(doc) {
  const state = EditorState.create({
    doc,
    extensions: [
      sql({ dialect: DuckDB, schema: namespace(SCHEMA) }),
      columnCompletion(() => SCHEMA),
    ],
  });
  const context = new CompletionContext(state, doc.length, true);
  const options = {};
  for (const source of state.languageDataAt("autocomplete", doc.length)) {
    const result = typeof source === "function" ? source(context) : null;
    for (const option of result?.options ?? []) {
      options[option.label] = typeof option.apply === "string" ? option.apply : option.label;
    }
  }
  return options;
}

test("identifiers are quoted when they need to be", () => {
  assert.equal(identifier("task"), "task");
  assert.equal(identifier("duracion total (ms)"), '"duracion total (ms)"');
  assert.equal(identifier("Correctas"), '"Correctas"');
  assert.equal(identifier('a"b'), '"a""b"');
});

test("tables, with a dot in their name, are completed and quoted", () => {
  const options = complete("SELECT * FROM ");
  assert.equal(options.task_results, "task_results");
  assert.equal(options["bloom/stroop.csv"], '"bloom/stroop.csv"');
});

test("columns of the tables in the query are completed without a prefix", () => {
  const options = complete('SELECT * FROM "bloom/stroop.csv" WHERE dur');
  assert.equal(options["duracion total (ms)"], '"duracion total (ms)"');
  assert.equal(options.identificacion, "identificacion");
  // Not the columns of a table the query doesn't name.
  assert.equal(options.participant, undefined);
});

test("the column source is the same at every lookup", () => {
  // CodeMirror tells sources apart by identity: a new one at each lookup loses its results.
  const state = EditorState.create({ doc: "", extensions: [columnCompletion(() => SCHEMA)] });
  const sources = () => state.languageDataAt("autocomplete", 0);
  assert.equal(sources()[0], sources()[0]);
});

test("DuckDB keywords are completed", () => {
  assert.ok("SUMMARIZE" in complete("SUMM") || "summarize" in complete("SUMM"));
});
