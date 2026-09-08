// 知识库浏览 tab。
// 后端目前只暴露学科来源(/api/sources)，文档目录/上传接口待接，
// 这一步先把交互骨架立起来：按学科列出来、选中高亮、上传入口备位。
export default function KbTab({ sources, activeKb, onSelectKb, onUpload }) {
  return (
    <div className="tab-body">
      <div className="tab-bar-actions">
        <button onClick={onUpload}>＋ 上传文档</button>
      </div>
      <span className="sub-title">按学科浏览</span>
      <div className="kb-subjects">
        {sources.length === 0 ? (
          <div className="kb-empty">学科数据加载中…</div>
        ) : (
          sources.map((s) => (
            <button
              key={s}
              className={`kb-subject-item ${activeKb === s ? 'active' : ''}`}
              onClick={() => onSelectKb(s)}
            >
              <span>{s}</span>
              <span className="kb-doc-count">暂无已入库文档</span>
            </button>
          ))
        )}
      </div>
      <p className="kb-hint">
        文档目录与上传接口待后端接入后，这里按学科展示已入库内容并支持增量索引。
      </p>
    </div>
  )
}