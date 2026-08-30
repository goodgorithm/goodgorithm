import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Plugin } from "vite";

// Generates /updates.atom from src/content/updates.md at build time (and
// serves it from the dev server), so the feed can never drift from the page.
//
// Entry convention in updates.md: one entry per `## YYYY-MM-DD — Title`
// heading, newest first; everything down to the next such heading is that
// entry's body. Anything above the first entry heading (the page intro) is
// not part of the feed.
//
// The body -> HTML conversion below covers the same small markdown subset as
// src/lib/markdown.tsx (paragraphs, `- ` lists, `code`/**bold**/*italic*/
// [text](url)). There's no shared parser -- markdown.tsx returns React nodes,
// this needs an HTML string -- so keep the two in sync by hand if either's
// supported syntax changes.

const SITE_ORIGIN = "https://goodgorithm.com";
const UPDATES_URL = `${SITE_ORIGIN}/updates`;
const FEED_URL = `${SITE_ORIGIN}/updates.atom`;

const ENTRY_HEADING = /^##\s+(\d{4}-\d{2}-\d{2})\s*[—–-]\s*(.+?)\s*$/;
const INLINE = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*|\[([^\]]+)\]\(([^)]+)\)/g;

interface Entry {
  date: string;
  title: string;
  bodyLines: string[];
}

function escapeXml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(value: string): string {
  return escapeXml(value).replace(/"/g, "&quot;");
}

function renderInline(text: string): string {
  let out = "";
  let last = 0;
  let match: RegExpExecArray | null;
  INLINE.lastIndex = 0;
  while ((match = INLINE.exec(text)) !== null) {
    out += escapeXml(text.slice(last, match.index));
    if (match[1] !== undefined) out += `<code>${escapeXml(match[1])}</code>`;
    else if (match[2] !== undefined) out += `<strong>${escapeXml(match[2])}</strong>`;
    else if (match[3] !== undefined) out += `<em>${escapeXml(match[3])}</em>`;
    else out += `<a href="${escapeAttr(match[5])}">${escapeXml(match[4])}</a>`;
    last = INLINE.lastIndex;
  }
  return out + escapeXml(text.slice(last));
}

function bodyToHtml(bodyLines: string[]): string {
  const blocks: string[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (list.length === 0) return;
    blocks.push(`<ul>${list.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`);
    list = [];
  };

  for (const raw of bodyLines) {
    const line = raw.trim();
    if (line === "") {
      flushParagraph();
      flushList();
    } else if (line.startsWith("- ")) {
      flushParagraph();
      list.push(line.slice(2));
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return blocks.join("");
}

function parseEntries(markdown: string): Entry[] {
  const entries: Entry[] = [];
  let current: Entry | null = null;
  for (const line of markdown.split("\n")) {
    const match = line.match(ENTRY_HEADING);
    if (match) {
      current = { date: match[1], title: match[2].trim(), bodyLines: [] };
      entries.push(current);
    } else if (current) {
      current.bodyLines.push(line);
    }
  }
  return entries;
}

function slugify(title: string): string {
  return (
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "update"
  );
}

function cdata(html: string): string {
  return `<![CDATA[${html.replace(/]]>/g, "]]]]><![CDATA[>")}]]>`;
}

export function buildAtomFeed(markdown: string): string {
  const entries = parseEntries(markdown);
  const updated = entries.length > 0 ? `${entries[0].date}T00:00:00Z` : "1970-01-01T00:00:00Z";

  const lines = [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom">',
    "  <title>Goodgorithm updates</title>",
    `  <id>${UPDATES_URL}</id>`,
    `  <link rel="alternate" href="${UPDATES_URL}"/>`,
    `  <link rel="self" href="${FEED_URL}"/>`,
    "  <author><name>Goodgorithm</name></author>",
    `  <updated>${updated}</updated>`,
  ];

  for (const entry of entries) {
    lines.push(
      "  <entry>",
      `    <title>${escapeXml(entry.title)}</title>`,
      `    <id>tag:goodgorithm.com,${entry.date}:${slugify(entry.title)}</id>`,
      `    <link rel="alternate" href="${UPDATES_URL}"/>`,
      `    <updated>${entry.date}T00:00:00Z</updated>`,
      `    <content type="html">${cdata(bodyToHtml(entry.bodyLines))}</content>`,
      "  </entry>",
    );
  }

  lines.push("</feed>", "");
  return lines.join("\n");
}

export function updatesFeedPlugin(): Plugin {
  const updatesMd = fileURLToPath(new URL("../src/content/updates.md", import.meta.url));
  const render = () => buildAtomFeed(readFileSync(updatesMd, "utf8"));
  return {
    name: "updates-feed",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url !== "/updates.atom") return next();
        res.setHeader("Content-Type", "application/atom+xml; charset=utf-8");
        res.end(render());
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "updates.atom", source: render() });
    },
  };
}
