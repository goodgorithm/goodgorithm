// Attachment/QuoteContent are hand-duplicated from api/src/types.ts -- same
// Railway rootDirectory-scoping reason api/ and web/ can't share a live
// package (see CLAUDE.md's Versioning & migration section): a labeller
// needs to see the same link-card/image/quote content the algorithm scores,
// not just bare text, so this tool captures it in the same shape rather than
// inventing a different one.

export type Source = "bluesky" | "mastodon";

export type QuoteContent =
  | {
      status: "available";
      author: { displayName: string | null; handle: string | null; avatarUrl: string | null };
      text: string;
      createdAt: string | null;
    }
  | { status: "unavailable"; reason: "not_found" | "filtered" };

export type Attachment =
  | {
      kind: "image";
      thumbnailUrl: string;
      fullUrl: string;
      alt: string | null;
      width: number | null;
      height: number | null;
    }
  | {
      kind: "link";
      url: string;
      title: string | null;
      description: string | null;
      thumbnailUrl: string | null;
      providerName: string | null;
    }
  | {
      kind: "video";
      playlistUrl: string;
      thumbnailUrl: string | null;
      isGif: boolean;
      width: number | null;
      height: number | null;
    }
  | { kind: "quote"; url: string; content: QuoteContent | null };

export interface Category {
  id: string;
  label: string;
  color: string;
}

export interface Study {
  id: string;
  slug: string;
  name: string;
  categories: Category[];
  created_at: string;
}

export interface LabelingPost {
  id: string;
  study_id: string;
  source: Source | null;
  rank_score: number | null;
  original_created_at: string | null;
  text: string;
  hashtags: string[];
  attachments: Attachment[] | null;
  quote_content: QuoteContent | null;
  batch: string | null;
  created_at: string;
}

export interface Label {
  id: string;
  post_id: string;
  reviewer: string; // 'ai' | 'maintainer' today; free text, room to grow
  category: string;
  taxonomy_flag: boolean;
  notes: string;
  created_at: string;
}

// A post plus the two labels the review UI actually needs: the AI's latest
// suggestion (to pre-highlight) and the maintainer's latest answer if one
// exists (to show as selected / to know whether it's still "unreviewed").
export interface PostWithLabels extends LabelingPost {
  ai_label: Pick<Label, "category"> | null;
  maintainer_label: Pick<Label, "category" | "taxonomy_flag" | "notes"> | null;
}
