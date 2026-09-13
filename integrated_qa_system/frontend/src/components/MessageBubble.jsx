import { Marked } from 'marked'
import DOMPurify from 'dompurify'

const md = new Marked({ breaks: true, gfm: true })

// 渲染前把 [N] 引用标记换成可点击的 .cite（data-cite 指向对应来源卡片序号）。
// 在 sanitize 之后替换，替换串是我们控制的 span，安全。
function renderMarkdown(text, sources) {
  let html = md.parse(text || '')
  if (sources && sources.length) {
    html = html.replace(/\[(\d+)\]/g, '<sup class="cite" data-cite="$1">[$1]</sup>')
  }
  return { __html: DOMPurify.sanitize(html) }
}

export default function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'
  const hasSources = !isUser && msg.sources && msg.sources.length

  return (
    <div className={`msg ${isUser ? 'user' : 'assistant'}`} data-mid={msg.id}>
      <div className="avatar">{isUser ? '我' : 'AI'}</div>
      <div className="msg-col">
        <div className="bubble">
          <div className="msg-body" dangerouslySetInnerHTML={renderMarkdown(msg.text, msg.sources)} />
          {!isUser && msg.streaming && <span className="cursor-blink" aria-hidden="true" />}
        </div>
        {hasSources && (
          <div className="sources-block">
            <div className="sources-label">参考来源 · {msg.sources.length} 条</div>
            {msg.sources.map((s) => (
              <a key={s.index} className="source-card" data-cite={s.index} href={s.url || '#'}>
                <div className="source-idx">{s.index}</div>
                <div className="source-body">
                  <div className="source-title">{s.title || '未命名文档'}</div>
                  {s.snippet && <div className="source-snippet">{s.snippet}</div>}
                  <div className="source-subject">主题：{s.subject}</div>
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}