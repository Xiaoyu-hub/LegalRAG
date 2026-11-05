import type { DocStatus } from "../types";

const LABEL: Record<DocStatus, string> = {
  processing: "索引中",
  ready: "就绪",
  error: "失败",
  unknown: "未知",
};

/** 文档状态徽标：颜色只表达状态，不额外加图标。 */
export default function StatusBadge({ status }: { status: DocStatus }) {
  return <span className={`badge ${status}`}>{LABEL[status] ?? status}</span>;
}

export function bytes(n: number): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function num(n: number | undefined | null): string {
  if (n === undefined || n === null) return "—";
  return n.toLocaleString("en-US");
}
