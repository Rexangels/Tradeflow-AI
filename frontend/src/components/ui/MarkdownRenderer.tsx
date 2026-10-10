import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * MarkdownRenderer
 * Renders AI responses with proper Markdown formatting using react-markdown.
 * Styled to match the TradeFlow AI dark theme.
 */
export function MarkdownRenderer({ content, className = "" }: MarkdownRendererProps) {
  const components: Components = {
    // Headings
    h1: ({ children }) => (
      <h1 className="text-base font-black text-slate-100 mt-3 mb-1.5 border-b border-slate-700 pb-1">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-sm font-bold text-slate-100 mt-3 mb-1">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-xs font-bold text-cyan-300 mt-2.5 mb-1 uppercase tracking-wide">
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-xs font-semibold text-slate-200 mt-2 mb-0.5">
        {children}
      </h4>
    ),

    // Paragraphs
    p: ({ children }) => (
      <p className="text-xs leading-relaxed mb-2 last:mb-0 text-inherit">
        {children}
      </p>
    ),

    // Strong / Bold
    strong: ({ children }) => (
      <strong className="font-bold text-slate-100">{children}</strong>
    ),

    // Emphasis / Italic
    em: ({ children }) => (
      <em className="italic text-slate-300">{children}</em>
    ),

    // Unordered lists
    ul: ({ children }) => (
      <ul className="list-disc list-outside pl-4 mb-2 space-y-0.5 text-xs">
        {children}
      </ul>
    ),

    // Ordered lists
    ol: ({ children }) => (
      <ol className="list-decimal list-outside pl-4 mb-2 space-y-0.5 text-xs">
        {children}
      </ol>
    ),

    li: ({ children }) => (
      <li className="leading-relaxed text-slate-300 pl-0.5">{children}</li>
    ),

    // Code — react-markdown v8 uses className to detect inline vs block
    code: ({ className: cls, children }) => {
      const isInline = !cls;
      if (isInline) {
        return (
          <code className="rounded bg-slate-800 border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300">
            {children}
          </code>
        );
      }
      return (
        <code className="block w-full font-mono text-[10px] text-emerald-300 overflow-x-auto whitespace-pre p-3">
          {children}
        </code>
      );
    },

    // Code blocks (pre wrapper)
    pre: ({ children }) => (
      <pre className="mb-2 overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
        {children}
      </pre>
    ),

    // Blockquotes
    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-cyan-500/60 pl-3 my-2 text-slate-400 italic">
        {children}
      </blockquote>
    ),

    // Horizontal rule
    hr: () => <hr className="my-3 border-slate-700" />,

    // Links
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300 transition-colors"
      >
        {children}
      </a>
    ),

    // Tables (from remark-gfm)
    table: ({ children }) => (
      <div className="overflow-x-auto my-2">
        <table className="w-full border-collapse text-[10px]">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-slate-800/80 text-slate-300 uppercase tracking-wider">
        {children}
      </thead>
    ),
    tbody: ({ children }) => (
      <tbody className="divide-y divide-slate-800">{children}</tbody>
    ),
    tr: ({ children }) => (
      <tr className="hover:bg-slate-800/30 transition-colors">{children}</tr>
    ),
    th: ({ children }) => (
      <th className="px-2 py-1 text-left font-semibold text-slate-300 border-b border-slate-700">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-2 py-1 text-slate-400">{children}</td>
    ),
  };

  return (
    <div className={`markdown-body ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
