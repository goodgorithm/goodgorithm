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

  it("renders bold, italic, and link inline formatting", () => {
    render(<Markdown source="Some **bold**, some *italic*, and a [link](https://example.com)." />);

    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    const link = screen.getByRole("link", { name: "link" });
    expect(link).toHaveAttribute("href", "https://example.com");
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
});
