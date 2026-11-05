import type { ReactNode } from "react";

import type { Citation } from "../types";

// 与后端 backend/generation/citation_builder.py 的 CITATION_PATTERN 保持同源，
// 改一边必须改另一边：前端高亮错位会让人误判「引用无效」。
const CITE_RE = /\[Article\s+(?:[IVXLCDM]+|\d+)(?:,\s*Section\s+\d+(?:\([a-z]\))?)?\]/gi;
// 后端把校验失败的引用替换成这句提示（见 CitationBuilder.mark_invalid）
const NEEDS_VERIFY = "[Citation needs verification]";

interface Props {
  content: string;
  citations?: Citation[];
  onCiteClick?: (text: string) => void;
}

/**
 * 渲染答案正文：把 `[Article X, Section Y]` 变成可点的高亮标签。
 *
 * 失效引用（后端校验为 valid=false 的）画成红色删除线 —— 「模型编了个条文号」
 * 这件事必须在界面上看得见，而不是只写进日志。
 */
export default function Answer({ content, citations = [], onCiteClick }: Props) {
  const invalid = new Set(
    citations.filter((c) => !c.valid).map((c) => c.text.replace(/\s+/g, " ").trim().toLowerCase()),
  );

  const parts: ReactNode[] = [];
  let last = 0;
  const text = content || "";

  const pushText = (chunk: string, key: string) => {
    if (!chunk) return;
    const segments = chunk.split(NEEDS_VERIFY);
    segments.forEach((segment, i) => {
      if (i > 0) {
        parts.push(
          <span key={`${key}-nv-${i}`} className="cite invalid" title="该引用没有在召回片段中找到">
            [引用未通过校验]
          </span>,
        );
      }
      if (segment) parts.push(segment);
    });
  };

  let match: RegExpExecArray | null;
  CITE_RE.lastIndex = 0;
  while ((match = CITE_RE.exec(text)) !== null) {
    pushText(text.slice(last, match.index), `t-${match.index}`);
    const raw = match[0];
    const key = raw.replace(/\s+/g, " ").trim().toLowerCase();
    const bad = invalid.has(key);
    parts.push(
      <span
        key={`c-${match.index}`}
        className={`cite${bad ? " invalid" : ""}`}
        title={bad ? "该条文号不在召回片段里" : "点击定位来源片段"}
        onClick={() => onCiteClick?.(raw)}
      >
        {raw}
      </span>,
    );
    last = match.index + raw.length;
  }
  pushText(text.slice(last), "t-end");

  return <div className="bubble">{parts}</div>;
}
