import type { ReactNode } from "react";

// A hand-rolled subset renderer, not a general CommonMark parser - covers
// exactly what the project's static content pages (mission, and the
// upcoming content policy - see issue #4) use: #/## headings, paragraphs,
// "- " lists, and inline **bold**/*italic*/[text](url). Not worth a
// markdown dependency for two static pages (no markdown lib exists
// anywhere in this repo today).
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const pattern = /\*\*(.+?)\*\*|\*(.+?)\*|\[(.+?)\]\((.+?)\)/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    if (match[1] !== undefined) {
      nodes.push(<strong key={`${keyPrefix}-${key++}`}>{match[1]}</strong>);
    } else if (match[2] !== undefined) {
      nodes.push(<em key={`${keyPrefix}-${key++}`}>{match[2]}</em>);
    } else {
      nodes.push(
        <a key={`${keyPrefix}-${key++}`} href={match[4]} target="_blank" rel="noreferrer">
          {match[3]}
        </a>,
      );
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

export function Markdown({ source }: { source: string }): ReactNode {
  const lines = source.trim().split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let blockKey = 0;
  const nextKey = () => blockKey++;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const key = nextKey();
    blocks.push(<p key={key}>{renderInline(paragraph.join(" "), `p${key}`)}</p>);
    paragraph = [];
  };

  const flushList = () => {
    if (list.length === 0) return;
    const key = nextKey();
    blocks.push(
      <ul key={key}>
        {list.map((item, i) => (
          <li key={i}>{renderInline(item, `l${key}-${i}`)}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "") {
      flushParagraph();
      flushList();
    } else if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      const key = nextKey();
      blocks.push(<h2 key={key}>{renderInline(line.slice(3), `h${key}`)}</h2>);
    } else if (line.startsWith("# ")) {
      flushParagraph();
      flushList();
      const key = nextKey();
      blocks.push(<h1 key={key}>{renderInline(line.slice(2), `h${key}`)}</h1>);
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

  return <>{blocks}</>;
}
