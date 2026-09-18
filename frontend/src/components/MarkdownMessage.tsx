import type { ReactNode } from "react";
import type { Components } from "react-markdown";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { hideInternalEvidenceIds, normalizeChatMarkdown } from "../markdown";

type MarkdownMessageProps = {
  text: string;
  className?: string;
  titlesById?: Record<string, string>;
};

function normalizeMarkdown(text: string): string {
  return normalizeChatMarkdown(text);
}

function omitNode<T extends { node?: unknown; children?: ReactNode }>(props: T) {
  const { node: _node, ...rest } = props;
  return rest;
}

const markdownComponents: Components = {
  h1: (props) => <h1 {...omitNode(props)} />,
  h2: (props) => <h2 {...omitNode(props)} />,
  h3: (props) => <h3 {...omitNode(props)} />,
  h4: (props) => <h4 {...omitNode(props)} />,
  p: (props) => <p {...omitNode(props)} />,
  ul: (props) => <ul {...omitNode(props)} />,
  ol: (props) => <ol {...omitNode(props)} />,
  li: (props) => <li {...omitNode(props)} />,
  strong: (props) => <strong {...omitNode(props)} />,
  em: (props) => <em {...omitNode(props)} />,
  a: ({ href, ...props }) => (
    <a href={href} target="_blank" rel="noreferrer" {...omitNode(props)} />
  ),
  table: (props) => (
    <div className="markdown-table-wrap">
      <table {...omitNode(props)} />
    </div>
  ),
  thead: (props) => <thead {...omitNode(props)} />,
  tbody: (props) => <tbody {...omitNode(props)} />,
  tr: (props) => <tr {...omitNode(props)} />,
  th: (props) => <th {...omitNode(props)} />,
  td: (props) => <td {...omitNode(props)} />,
  br: () => <br />,
  hr: (props) => <hr {...omitNode(props)} />,
  blockquote: (props) => <blockquote {...omitNode(props)} />,
};

export function MarkdownMessage({ text, className, titlesById }: MarkdownMessageProps) {
  const markdown = hideInternalEvidenceIds(normalizeMarkdown(text), titlesById);
  return (
    <div
      className={className ? `markdown-body ${className}` : "markdown-body"}
      data-testid="assistant-markdown"
    >
      <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {markdown}
      </Markdown>
    </div>
  );
}
