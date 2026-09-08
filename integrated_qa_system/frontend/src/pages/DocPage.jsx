import { useParams, Link } from 'react-router-dom'

// 文档详情页：承接引用溯源可视化。
// 后端文档详情接口待接后，展示全文 + 命中片段高亮 + 章节树。
export default function DocPage() {
  const { docId } = useParams()
  return (
    <div className="doc-page">
      <div className="doc-toolbar">
        <Link to="/kb" className="back-link">← 返回知识库</Link>
        <span className="sub-title">文档详情</span>
      </div>
      <div className="doc-body">
        <h2>文档 #{docId}</h2>
        <p className="kb-hint">
          后端文档详情接口待接入。这里将展示：所属学科、章节结构、全文，以及 RAG
          检索命中的片段高亮，用于核对「引用溯源」的出处。
        </p>
      </div>
    </div>
  )
}