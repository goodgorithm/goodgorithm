import type { ReactNode } from "react";

// A hand-rolled subset renderer, not a general CommonMark parser - covers
// exactly what the project's static content pages (mission, content
// policy, algorithm) use: #/## headings, paragraphs, "- " lists, ``` code
// fences (verbatim, no inline parsing inside), and inline
// `code`/**bold**/*italic*/[text](url). Not worth a markdown dependency
// for a handful of static pages (no markdown lib exists anywhere in this
// repo today).
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  // `code` first: content between single backticks (e.g. `raw_posts`)
  // must never fall through to the bold/italic/link alternatives, even
  // if it happens to contain * or [ characters.
  const pattern = /`(.+?)`|\*\*(.+?)\*\*|\*(.+?)\*|\[(.+?)\]\((.+?)\)/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    if (match[1] !== undefined) {
      nodes.push(<code key={`${keyPrefix}-${key++}`}>{match[1]}</code>);
    } else if (match[2] !== undefined) {
      nodes.push(<strong key={`${keyPrefix}-${key++}`}>{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      nodes.push(<em key={`${keyPrefix}-${key++}`}>{match[3]}</em>);
    } else {
      nodes.push(
        <a key={`${keyPrefix}-${key++}`} href={match[5]} target="_blank" rel="noreferrer">
          {match[4]}
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
  let codeBlock: string[] | null = null;
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

    if (codeBlock !== null) {
      if (line.startsWith("```")) {
        blocks.push(
          <pre key={nextKey()}>
            <code>{codeBlock.join("\n")}</code>
          </pre>,
        );
        codeBlock = null;
      } else {
        codeBlock.push(rawLine);
      }
      continue;
    }

    if (line === "") {
      flushParagraph();
      flushList();
    } else if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      codeBlock = [];
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
  if (codeBlock !== null) {
    // unterminated fence -- render what we have rather than silently drop it
    blocks.push(
      <pre key={nextKey()}>
        <code>{codeBlock.join("\n")}</code>
      </pre>,
    );
  }

  return <>{blocks}</>;
}
