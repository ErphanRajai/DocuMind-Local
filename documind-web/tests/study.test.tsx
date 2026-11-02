import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Answer } from "../components/answer";
import { equationPreview, dueItems, generatedPracticePrompt } from "../lib/study";
import { restoreWorkspaces } from "../lib/workspaces";
import {mergeWorkspaceCopies} from '../lib/persistence';

describe("Mathematical answers", () => {
  it("renders accessible inline/display math and keeps citations clickable", () => {
    const source = {
      id: "S1",
      pdf_id: 1,
      page: 2,
      filename: "notes.pdf",
      excerpt: "Quadratic formula",
    };
    const open = vi.fn();
    const { container } = render(
      <Answer
        text={"Use $x^2$ [S1].\n\n$$\\frac{1}{2}$$"}
        sources={[source]}
        onSource={open}
      />,
    );
    expect(container.querySelectorAll(".katex").length).toBe(2);
    expect(container.querySelector("math")).not.toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Open source S1, PDF page 2" }),
    );
    expect(open).toHaveBeenCalledWith(source);
  });
  it("does not activate an HTML link command inside untrusted math", () => {
    const { container } = render(
      <Answer
        text={"$$\\href{javascript:alert(1)}{click}$$"}
        sources={[]}
        onSource={() => {}}
      />,
    );
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });
  it("handles incomplete equations without crashing", () => {
    const { container } = render(
      <Answer text={"Working: $\\frac{1}{"} sources={[]} onSource={() => {}} />,
    );
    expect(container.textContent).toContain("Working");
  });
  it("preserves literal mathematical source in code", () => {
    const { container } = render(
      <Answer text={"`$x^2$ [S1]`"} sources={[]} onSource={() => {}} />,
    );
    expect(container.querySelector(".katex")).toBeNull();
  });
});
describe("Study state", () => {
  it('typesets known generated practice without rewriting arbitrary saved wording',()=>{
    const item={id:'p',workspace_id:'w',kind:'practice',data:{origin:'Generated calculator exercise; not extracted from a PDF.',result:{input:{operation:'solve',expression:'x^2-5*x+6=0'}}}};
    const prompt=generatedPracticePrompt(item)!;
    const {container}=render(<Answer text={prompt.markdown} sources={[]} onSource={()=>{}}/>);
    expect(prompt.label).toBe('Solve');
    expect(container.querySelector('.katex')).not.toBeNull();
    expect(generatedPracticePrompt({...item,data:{question:'Keep my own notation'}})).toBeNull();
  });
  it('preserves browser-only work and forks conflicting histories instead of overwriting them',()=>{
    const base={id:'w',title:'Notes',documents:[],messages:[],updated:1};
    const local={...base,messages:[{id:'u',role:'user' as const,content:'A browser-only question'}]};
    const result=mergeWorkspaceCopies([base],[local,{...base,id:'local-only'}]);
    expect(result).toHaveLength(3);expect(result[1].id).not.toBe('w');expect(result[1].messages[0].content).toBe('A browser-only question');
    expect(mergeWorkspaceCopies([base],[base])).toHaveLength(1);
    expect(mergeWorkspaceCopies([], [base], [base.id])).toEqual([]);
  });
  it("shows equations in preview notation", () =>
    expect(equationPreview("2*x**2+sqrt(x)+pi")).toBe(
      "2\\cdot x^2+\\sqrt{x}+\\pi ",
    ));
  it("schedules only due reviewable items", () => {
    const rows = [
      {
        id: "a",
        kind: "formula",
        workspace_id: "w",
        data: { due: "2020-01-01" },
      },
      {
        id: "b",
        kind: "mistake",
        workspace_id: "w",
        data: { due: "2100-01-01" },
      },
      { id: "c", kind: "attempt", workspace_id: "w", data: {} },
    ];
    expect(dueItems(rows, Date.parse("2026-01-01")).map((i) => i.id)).toEqual([
      "a",
    ]);
  });
  it("imports valid exported workspaces", () => {
    expect(
      restoreWorkspaces(
        JSON.stringify([
          { id: "a", title: "Exam", messages: [], documents: [], updated: 1 },
        ]),
      )[0].title,
    ).toBe("Exam");
  });
});
