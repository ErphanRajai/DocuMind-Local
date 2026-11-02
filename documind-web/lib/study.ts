export type StudyItem = {
  id: string;
  kind: string;
  workspace_id: string;
  data: Record<string, unknown>;
};
export type MathInput = {
  operation: string;
  expression: string;
  variable: string;
  domain: string;
  equations?: string[];
  variables?: string[];
  expected?: string;
  working?: string[];
  lower?: string;
  upper?: string;
  matrix?: number[][];
  matrix_action?: string;
  magnitude?: number;
  from_unit?: string;
  to_unit?: string;
};
export type Calculation = {
  operation: string;
  input: MathInput;
  result: string;
  latex: string;
  verified: boolean;
  checks: { label: string; passed: boolean }[];
  steps: string[];
  working_checks: { step: number; passed: boolean; label: string }[];
  assumptions: string[];
  engine: string;
};
export type PaperQuestion = {
  number: string;
  text: string;
  pdf_id: number;
  page: number;
  marks: number | null;
  subparts: string[];
};
export function equationPreview(value: string) {
  return value
    .replaceAll("**", "^")
    .replaceAll("*", "\\cdot ")
    .replaceAll("pi", "\\pi ")
    .replace(/sqrt\(([^()]+)\)/g, "\\sqrt{$1}");
}

export function inputMarkdown(input: MathInput) {
  if (input.operation === "units")
    return `Convert **${input.magnitude} ${input.from_unit}** to **${input.to_unit}**.`;
  if (input.operation === "matrix")
    return `$$\n\\begin{bmatrix}${(input.matrix || []).map((row) => row.join("&")).join("\\\\")}\\end{bmatrix}\n$$\n\nOperation: ${input.matrix_action || "determinant"}.`;
  const expressions = input.equations?.length
    ? input.equations
    : [input.expression];
  return (
    expressions
      .map((value) => `$$\n${equationPreview(value)}\n$$`)
      .join("\n\n") +
    `\n\nOperation: ${input.operation}. Variable: ${input.variable}. Domain: ${input.domain || "real"}.`
  );
}
export function dueItems(items: StudyItem[], now = Date.now()) {
  return items.filter(
    (i) =>
      ["mistake", "practice", "formula"].includes(i.kind) &&
      (!i.data.due || Date.parse(String(i.data.due)) <= now),
  );
}

export function generatedPracticePrompt(item: StudyItem) {
  if (item.kind !== "practice" || item.data.origin !== "Generated calculator exercise; not extracted from a PDF.") return null;
  const input = (item.data.result as { input?: MathInput } | undefined)?.input;
  const labels: Record<string, string> = { solve: "Solve", differentiate: "Differentiate", integrate: "Integrate" };
  if (!input || typeof input.expression !== "string" || !labels[input.operation]) return null;
  return { label: labels[input.operation], markdown: `$$\n${equationPreview(input.expression)}\n$$` };
}

export function staleEvidence(
  data: Record<string, unknown>,
  versions: Record<number, string>,
) {
  const recorded = (
    data.metrics as
      | { document_versions?: { pdf_id: number; text_sha256: string }[] }
      | undefined
  )?.document_versions;
  return (
    Array.isArray(recorded) &&
    recorded.some(
      (v) => versions[v.pdf_id] && versions[v.pdf_id] !== v.text_sha256,
    )
  );
}
