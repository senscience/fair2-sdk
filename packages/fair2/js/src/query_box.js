// The SQL editor of fair2.query_box: an anywidget (https://anywidget.dev) around CodeMirror 6.
//
// The model has `query` (the editor's text) and `schema` (table name -> column names, from the
// DuckDB catalog). Running sends a "run" message: Python executes the query and shows the result
// under the editor. Exporting, Python sends a "download" message with the file: it is saved by the
// browser. Completion: SQL keywords (PostgreSQL's, with DuckDB's own), table names, and
// the columns of the tables the query names, quoted when they need to be.
import { autocompletion, completionKeymap } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { PostgreSQL, SQLDialect, sql } from "@codemirror/lang-sql";
import { bracketMatching, syntaxHighlighting, defaultHighlightStyle } from "@codemirror/language";
import { Compartment, EditorState, Prec } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, placeholder } from "@codemirror/view";

// DuckDB: PostgreSQL's syntax, and keywords of its own.
const DuckDB = SQLDialect.define({
  ...PostgreSQL.spec,
  keywords: `${PostgreSQL.spec.keywords} summarize describe pivot unpivot qualify exclude replace columns pragma attach detach install load`,
});

// An identifier as SQL needs it: quoted unless it is a plain lower-case name.
function identifier(name) {
  return /^[a-z_][a-z_0-9]*$/.test(name) ? name : `"${name.replace(/"/g, '""')}"`;
}

// The schema for lang-sql: a dot in a name separates a schema from a table, so dots are escaped.
function namespace(schema) {
  return Object.fromEntries(
    Object.entries(schema).map(([table, columns]) => [table.replace(/\./g, "\\."), columns]),
  );
}

// The columns of the tables named in the query, without the table prefix lang-sql requires.
function columnsOfNamedTables(getSchema) {
  return (context) => {
    const word = context.matchBefore(/"?[\wÀ-ɏ]*$/);
    if (!word || (word.from === word.to && !context.explicit)) return null;
    const text = context.state.doc.toString();
    const options = [];
    const seen = new Set();
    for (const [table, columns] of Object.entries(getSchema())) {
      if (!text.includes(identifier(table)) && !text.includes(table)) continue;
      for (const column of columns) {
        if (seen.has(column)) continue;
        seen.add(column);
        options.push({ label: column, apply: identifier(column), type: "property", detail: table });
      }
    }
    // The closing quote is part of the applied text: don't leave the one the editor added.
    const closing = context.state.sliceDoc(context.pos, context.pos + 1) === '"';
    return options.length
      ? { from: word.from, to: closing ? context.pos + 1 : context.pos, options, validFor: /^"?[\wÀ-ɏ]*$/ }
      : null;
  };
}

// Colours from the notebook's theme (JupyterLab variables), with light fallbacks elsewhere.
const theme = EditorView.theme({
  "&": {
    backgroundColor: "var(--jp-cell-editor-background, #fcfcfb)",
    color: "var(--jp-content-font-color1, #1a1a19)",
    border: "1px solid var(--jp-border-color1, #d5d5d5)",
    borderRadius: "6px",
    fontSize: "var(--jp-code-font-size, 13px)",
  },
  "&.cm-focused": { outline: "2px solid var(--jp-brand-color1, #3673f7)", outlineOffset: "-1px" },
  ".cm-content": { fontFamily: "var(--jp-code-font-family, ui-monospace, monospace)", minHeight: "5.5em" },
  ".cm-gutters": {
    backgroundColor: "transparent",
    color: "var(--jp-ui-font-color2, #878787)",
    border: "none",
  },
  ".cm-tooltip-autocomplete": { fontFamily: "var(--jp-code-font-family, ui-monospace, monospace)" },
});

// The language data adding the column completion. Created once: CodeMirror tells completion
// sources apart by identity, and a new function at each lookup would discard its results.
function columnCompletion(getSchema) {
  const data = [{ autocomplete: columnsOfNamedTables(getSchema) }];
  return EditorState.languageData.of(() => data);
}

// Saves a file sent by Python: {type: "download", name, mime}, and its bytes as the first buffer.
function download(message, buffers) {
  if (message.type !== "download" || !buffers?.length) return;
  const url = URL.createObjectURL(new Blob([buffers[0]], { type: message.mime }));
  const link = Object.assign(document.createElement("a"), { href: url, download: message.name });
  document.body.append(link);
  link.click();
  link.remove();
  // After the download has started.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function render({ model, el }) {
  const schema = new Compartment();
  const language = (tables) => sql({ dialect: DuckDB, schema: namespace(tables), upperCaseKeywords: true });

  const run = () => {
    model.set("query", view.state.doc.toString());
    model.save_changes();
    model.send({ type: "run" });
    return true;
  };

  const view = new EditorView({
    parent: el,
    state: EditorState.create({
      doc: model.get("query"),
      extensions: [
        lineNumbers(),
        history(),
        bracketMatching(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        schema.of(language(model.get("schema"))),
        columnCompletion(() => model.get("schema")),
        autocompletion(),
        // Before the default keys: Ctrl/Cmd+Enter runs instead of inserting a line.
        Prec.highest(keymap.of([{ key: "Mod-Enter", run }])),
        keymap.of([...completionKeymap, ...defaultKeymap, ...historyKeymap]),
        placeholder("SELECT … FROM …"),
        EditorView.lineWrapping,
        theme,
      ],
    }),
  });

  const bar = document.createElement("div");
  bar.className = "fair2-query-bar";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Run";
  button.addEventListener("click", run);
  const hint = document.createElement("span");
  hint.textContent = "Ctrl/Cmd+Enter to run · Ctrl+Space for completions";
  bar.append(button, hint);
  el.append(bar);

  // New tables (a query can create some): update the completions.
  const onSchema = () => view.dispatch({ effects: schema.reconfigure(language(model.get("schema"))) });
  model.on("change:schema", onSchema);
  model.on("msg:custom", download);
  return () => {
    model.off("change:schema", onSchema);
    model.off("msg:custom", download);
    view.destroy();
  };
}

export default { render };
// For the tests (test/completion.test.js).
export { DuckDB, columnCompletion, columnsOfNamedTables, identifier, namespace };
