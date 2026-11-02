"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export function mathMarkdown(text: string) {
  // Preserve code and display equations; escape clear currency amounts before
  // Markdown's inline-math tokenizer can pair two unrelated dollar signs.
  return text
    .split(/(```[\s\S]*?(?:```|$)|`[^`]*`|\$\$[\s\S]*?(?:\$\$|$))/g)
    .map((part, index) =>
      index % 2
        ? part
        : part.replace(
            /(?<!\\)\$(?=\d[\d,.]*(?:\s+(?:and|per|for|USD|dollars|each|is|to|in|on|budget)\b|[.,;:!?](?:\s|$)|$))/g,
            "\\$",
          ),
    )
    .join("")
    .split(/(```[\s\S]*?(?:```|$)|`[^`]*`)/g)
    .map((part, index) =>
      index % 2
        ? part
        : part
            .replace(/\\\[([\s\S]*?)\\\]/g, (_, body) => `\n$$\n${body}\n$$\n`)
            .replace(/\\\(([^\n]*?)\\\)/g, (_, body) => `$${body}$`),
    )
    .join("");
}
import type { Source } from "../lib/types";
type Node = { type: string; value?: string; url?: string; children?: Node[] };
export function identifierPlugin() {
  return (tree: Node) => {
    function walk(node: Node) {
      if (
        !node.children ||
        ["code", "inlineCode", "link", "html", "math", "inlineMath"].includes(
          node.type,
        )
      )
        return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text" || !child.value) {
          walk(child);
          return [child];
        }
        const parts: Node[] = [];
        let last = 0;
        for (const match of child.value.matchAll(
          /\b[A-Z]{2,}[A-Z0-9]*(?:[-_][A-Z0-9]{2,})+\b/g,
        )) {
          parts.push(
            { type: "text", value: child.value.slice(last, match.index) },
            { type: "inlineCode", value: match[0] },
          );
          last = match.index! + match[0].length;
        }
        return parts.length
          ? [...parts, { type: "text", value: child.value.slice(last) }]
          : [child];
      });
    }
    walk(tree);
  };
}
export function citationPlugin(sources: Source[]) {
  return () => (tree: Node) => {
    const ids = new Set(sources.map((s) => s.id));
    function walk(node: Node) {
      if (
        !node.children ||
        ["code", "inlineCode", "link", "html"].includes(node.type)
      )
        return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text" || !child.value) {
          walk(child);
          return [child];
        }
        const parts: Node[] = [];
        let last = 0;
        for (const match of child.value.matchAll(
          /\[\s*((?:S|s|س)\s*[0-9۰-۹٠-٩]+)\s*\]/g,
        )) {
          const id = match[1]
            .replace(/\s/g, "")
            .replace(/^[sس]/, "S")
            .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 1776))
            .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 1632));
          if (!ids.has(id)) continue;
          const start = match.index!;
          parts.push(
            { type: "text", value: child.value.slice(last, start) },
            {
              type: "link",
              url: `#source-${id}`,
              children: [{ type: "text", value: id }],
            },
          );
          last = start + match[0].length;
        }
        return parts.length
          ? [...parts, { type: "text", value: child.value.slice(last) }]
          : [child];
      });
    }
    walk(tree);
  };
}
export function Answer({
  text,
  sources,
  onSource,
}: {
  text: string;
  sources: Source[];
  onSource: (s: Source) => void;
}) {
  return (
    <div className="answer" dir="auto">
      <ReactMarkdown
        remarkPlugins={[
          remarkGfm,
          remarkMath,
          citationPlugin(sources),
          identifierPlugin,
        ]}
        rehypePlugins={[
          [
            rehypeKatex,
            {
              trust: false,
              throwOnError: false,
              maxExpand: 100,
              maxSize: 20,
              output: "htmlAndMathml",
            },
          ],
        ]}
        components={{
          a: ({ href, children }) => {
            const source = sources.find((s) => href === `#source-${s.id}`);
            return source ? (
              <button
                className="citation"
                onClick={() => onSource(source)}
                title={`${source.filename} · PDF page ${source.page}`}
                aria-label={`Open source ${source.id}, PDF page ${source.page}`}
              >
                {source.id.slice(1)}
                <span>p. {source.page}</span>
              </button>
            ) : (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {mathMarkdown(text)}
      </ReactMarkdown>
    </div>
  );
}
