import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "../../src/lib/markdown";

describe("Markdown", () => {
  it("renders headings", () => {
    render(<Markdown source={"# Title\n\n## Section"} />);

    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Section" })).toBeInTheDocument();
  });

  it("renders paragraphs, joining wrapped lines", () => {
    render(<Markdown source={"First line\nsecond line\n\nNew paragraph"} />);

    expect(screen.getByText("First line second line")).toBeInTheDocument();
    expect(screen.getByText("New paragraph")).toBeInTheDocument();
  });

  it("renders inline code, bold, italic, and link formatting", () => {
    render(
      <Markdown source="Some `code`, some **bold**, some *italic*, and a [link](https://example.com)." />,
    );

    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    const link = screen.getByRole("link", { name: "link" });
    expect(link).toHaveAttribute("href", "https://example.com");
  });

  it("does not let inline-code content fall through to bold/italic/link parsing", () => {
    render(<Markdown source="See `array[0]` and `a*b*c` for reference." />);

    expect(screen.getByText("array[0]").tagName).toBe("CODE");
    expect(screen.getByText("a*b*c").tagName).toBe("CODE");
  });

  it("renders a bullet list", () => {
    render(<Markdown source={"- First item\n- Second item"} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("First item")).toBeInTheDocument();
    expect(screen.getByText("Second item")).toBeInTheDocument();
  });

  it("does not treat bold markers as unmatched italics", () => {
    render(<Markdown source="**Fully bold sentence.**" />);

    expect(screen.getByText("Fully bold sentence.").tagName).toBe("STRONG");
  });

  it("renders a fenced code block verbatim, without inline formatting", () => {
    render(<Markdown source={"```\nbase_score = a * b\n```"} />);

    const code = screen.getByText("base_score = a * b");
    expect(code.tagName).toBe("CODE");
    expect(code.parentElement?.tagName).toBe("PRE");
  });

  it("renders an unterminated code fence instead of dropping it", () => {
    render(<Markdown source={"```\nno closing fence"} />);

    expect(screen.getByText("no closing fence").tagName).toBe("CODE");
  });

  it("does not apply inline formatting inside a code block", () => {
    render(<Markdown source={"```\n**not bold**\n```"} />);

    expect(screen.getByText("**not bold**")).toBeInTheDocument();
    expect(screen.queryByText("not bold")).not.toBeInTheDocument();
  });
});
