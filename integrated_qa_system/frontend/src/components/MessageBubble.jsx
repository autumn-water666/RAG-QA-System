import { Marked } from 'marked'
import DOMPurify from 'dompurify'

const md = new Marked({ breaks: true, gfm: true })

// marked 产物先进 DOMPurify 防注入；若有来源，再给 [N] 引用标记套高亮样式。
// 在 sanitize 之后替换，替换串是我们控制的 span，安全。
function renderMarkdown(text, sources) {
  let html = md.parse(text || '')
  if (sources && sources.length) {
    html = html.replace(/\[(\d+)\]/g, '<span class="citation-marker">[$1]</span>')
  }
  return { __html: DOMPurify.sanitize(html) }
}

export default function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'

  // 加载中且还没有任何文本 → 打点动画
  const typing = isAssistantLoading(msg) ? (
    <span className="typing" aria-busy="true"><i /><i /><i /></span>
  ) : (
    <div className="markdown" dangerouslySetInnerHTML={renderMarkdown(msg.text, msg.sources)} />
  )

  return (
    <div className={`bubble ${isUser ? 'user' : 'assistant'}`}>
      {typing}
      {msg.sources && msg.sources.length > 0 && (
        <div className="sources-block">
          <span className="src-title">参考来源</span>
          {msg.sources.map((s, i) => (
            <a
              key={i}
              className="source-chip"
              href={s.url || '#'}
              target={s.url ? '_blank' : undefined}
              rel="noreferrer"
            >
              <span className="sc-idx">[{i + 1}]</span>
              {s.snippet ? (
                <span className="sc-column">
                  <span className="sc-title">{s.title || '未命名文档'}</span>
                  <span className="sc-snip">{s.snippet}</span>
                </span>
              ) : (
                <span className="sc-title">{s.title || '未命名文档'}</span>
              )}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function isAssistantLoading(msg) {
  return msg.role === 'assistant' && ((msg.loading && !msg.text) || (msg.streaming && !msg.text))
}