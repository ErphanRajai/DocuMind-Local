import type { Source } from "./types";
export function citedSources(answer: string, sources: Source[]) {
  const ids = new Set(
    Array.from(
      answer
        .replace(/```[\s\S]*?(?:```|$)|`[^`]*`/g, "")
        .matchAll(/\[\s*[Ssس]\s*([0-9۰-۹٠-٩]+)\s*\]/g),
      (m) =>
        "S" +
        m[1]
          .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 1776))
          .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 1632)),
    ),
  );
  return sources.filter((s) => ids.has(s.id));
}
