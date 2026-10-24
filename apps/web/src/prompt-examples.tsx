import { useState } from "react";
import singlePrompts from "./prompt-examples/single-prompts.md?raw";
import batchGuide from "./prompt-examples/batch-guide.md?raw";
import batchBlocks from "./prompt-examples/batch-blocks.md?raw";
import batchTable from "./prompt-examples/batch-table.md?raw";
import batchCsv from "./prompt-examples/batch.csv?raw";
import batchJson from "./prompt-examples/batch.json?raw";

type Example = { file: string; title: string; text: string; type: string };

const SINGLE: Example[] = [{ file: "single-prompts.md", title: "Single prompts · attribute checklist and examples", text: singlePrompts, type: "text/markdown" }];
const BATCH: Example[] = [
  { file: "batch-guide.md", title: "Batch guide · every field explained", text: batchGuide, type: "text/markdown" },
  { file: "batch-blocks.md", title: "Markdown heading blocks (long-form)", text: batchBlocks, type: "text/markdown" },
  { file: "batch-table.md", title: "Markdown table", text: batchTable, type: "text/markdown" },
  { file: "batch.csv", title: "CSV (all columns)", text: batchCsv, type: "text/csv" },
  { file: "batch.json", title: "JSON (all fields)", text: batchJson, type: "application/json" },
];

function download(example: Example) {
  const url = URL.createObjectURL(new Blob([example.text], { type: example.type + ";charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url; link.download = example.file; document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Downloadable prompt templates; the batch files import as-is (covered by tests/test_prompt_examples.py).
export function PromptExamples({ mode }: { mode: "single" | "batch" }) {
  const examples = mode === "single" ? [...SINGLE, BATCH[0]] : [...BATCH, SINGLE[0]];
  const [open, setOpen] = useState(examples[0].file);
  const shown = examples.find((e) => e.file === open) || examples[0];
  return (
    <details className="prompt-examples">
      <summary>Prompt examples <span>view or download templates with every attribute</span></summary>
      <div className="prompt-examples-list" role="tablist">
        {examples.map((e) => (
          <button key={e.file} type="button" role="tab" aria-selected={e.file === shown.file} className={e.file === shown.file ? "selected" : ""} onClick={() => setOpen(e.file)}>{e.title}</button>
        ))}
      </div>
      <div className="prompt-examples-actions">
        <strong>{shown.file}</strong>
        <button type="button" onClick={() => download(shown)}>Download</button>
        <button type="button" onClick={() => examples.forEach(download)}>Download all</button>
      </div>
      <pre className="prompt-examples-text" tabIndex={0}>{shown.text}</pre>
    </details>
  );
}
