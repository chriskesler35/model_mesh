/**
 * Lightweight markdown renderer — no external deps.
 * Returns HTML string, use with dangerouslySetInnerHTML.
 *
 * Supports: code blocks, inline code, bold, italic, headers, lists,
 * links, paragraph breaks.
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  return text
    // Escape HTML first
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Fenced code blocks
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) =>
      `<pre class="bg-gray-900 dark:bg-gray-950 text-gray-100 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono"><code>${code.trim()}</code></pre>`)
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-[0.9em] font-mono">$1</code>')
    // Bold (**text**)
    .replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>')
    // Italic (*text*) — careful not to match inside already-processed bold
    .replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-4 mb-1">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>')
    // Links [text](url)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer" class="text-indigo-500 hover:underline">$1</a>')
    // Bullet lists
    .replace(/^[*\-] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // Numbered lists
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // Wrap consecutive <li> into <ul>
    .replace(/(<li[^>]*>.*?<\/li>\s*)+/g, s => `<ul class="my-2 space-y-0.5">${s}</ul>`)
    // Paragraph breaks
    .replace(/\n\n/g, '</p><p class="mb-2">')
    // Single line breaks
    .replace(/\n/g, '<br/>')
}
