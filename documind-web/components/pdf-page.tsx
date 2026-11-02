"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
type Box = { x: number; y: number; w: number; h: number; text?: string };
type Geometry = { text: string; words: Box[]; highlights: Box[] };
export function PDFPage({
  id,
  page,
  filename,
  excerpt,
  onError,
}: {
  id: number;
  page: number;
  filename: string;
  excerpt?: string;
  onError: () => void;
}) {
  const [geometry, setGeometry] = useState<Geometry | null>(null),
    [search, setSearch] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setGeometry(null);
    const needle = search || excerpt?.replace(/\s+/g, " ").slice(0, 100) || "";
    api<Geometry>(
      `/summarizer/documents/${id}/pages/${page}/text?search=${encodeURIComponent(needle)}`,
      { signal: controller.signal },
    )
      .then((value) => {
        if (
          typeof value?.text === "string" &&
          Array.isArray(value.words) &&
          Array.isArray(value.highlights)
        )
          setGeometry(value);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [id, page, excerpt, search]);
  return (
    <div className="pdf-page-wrap">
      <label className="pdf-search">
        Find on this page
        <input
          aria-label="Find on this PDF page"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          maxLength={150}
          placeholder="Search a word or formula"
        />
      </label>
      <div className="selectable-pdf">
        <img
          src={`/api/summarizer/documents/${id}/pages/${page}.png`}
          alt={`Original PDF page ${page} of ${filename}`}
          onError={onError}
        />
        {geometry?.highlights.map((b, i) => (
          <mark
            key={i}
            aria-hidden="true"
            style={{
              left: `${b.x * 100}%`,
              top: `${b.y * 100}%`,
              width: `${b.w * 100}%`,
              height: `${b.h * 100}%`,
            }}
          />
        ))}
        <div className="pdf-text-layer" aria-hidden="true">
          {geometry?.words.map((b, i) => (
            <span
              key={i}
              style={{
                left: `${b.x * 100}%`,
                top: `${b.y * 100}%`,
                width: `${b.w * 100}%`,
                height: `${b.h * 100}%`,
              }}
            >
              {b.text}{" "}
            </span>
          ))}
        </div>
      </div>
      {geometry && (
        <details className="pdf-accessible-text">
          <summary>Selectable extracted text</summary>
          <p>
            {geometry.text ||
              "No selectable text on this page. Compare the scan with its OCR excerpt."}
          </p>
        </details>
      )}
    </div>
  );
}
