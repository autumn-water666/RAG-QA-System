from fastapi import FastAPI, WebSocket, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
import os
from pydantic import BaseModel
import asyncio
import threading
import json
import uuid
from typing import Optional, List, Dict, Any
import time
import re

# 导入现有的系统
from new_main import IntegratedQASystem
# 导入日志
from base import logger

# 当前文件所在目录，用于拼接静态文件绝对路径，避免 uvicorn 工作目录不同时找不到文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 创建应用实例
app = FastAPI(title="问答系统API", description="集成MySQL和RAG的智能问答系统")

# 配置CORS，允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建静态文件目录
os.makedirs(STATIC_DIR, exist_ok=True)

# 创建全局QA系统实例
qa_system = IntegratedQASystem()

# 定义日常问候用语模式和回复
GREETING_PATTERNS = [
    {
        "pattern": r"^(你好|您好|hi|hello)",
        "response": "你好！我是黑马程序员，专注于为学生答疑解惑，很高兴为你服务！"
    },
    {
        "pattern": r"^(你是谁|您是谁|你叫什么|你的名字|who are you)",
        "response": "我是黑马程序员，你的智能学习助手，致力于提供 IT 教育相关的解答！"
    },
    {
        "pattern": r"^(在吗|在不在|有人吗)",
        "response": "我在！我是黑马程序员，随时为你解答问题！"
    },
    {
        "pattern": r"^(干嘛呢|你在干嘛|做什么)",
        "response": "我正在待命，随时为你解答 IT 学习相关的问题！有什么我可以帮你的？"
    }
]

# 定义请求模型
class QueryRequest(BaseModel):
    query: str
    source_filter: Optional[str] = None
    session_id: Optional[str] = None

# 定义响应模型
class QueryResponse(BaseModel):
    answer: str
    is_streaming: bool
    session_id: str
    processing_time: float

# 创建新会话
@app.post("/api/create_session")
async def create_session():
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}

# 查询历史消息
@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    try:
        history = qa_system.get_session_history(session_id)
        return {"session_id": session_id, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {str(e)}")

# 清除历史消息
@app.delete("/api/history/{session_id}")
async def clear_history(session_id: str):
    success = qa_system.clear_session_history(session_id)
    if success:
        return {"status": "success", "message": "历史记录已清除"}
    else:
        raise HTTPException(status_code=500, detail="清除历史记录失败")


# 检查是否为日常问候用语并返回模板回复
def check_greeting(query: str) -> Optional[str]:
    query_text = query.strip()  # 去除 # 前缀
    for pattern_info in GREETING_PATTERNS:
        if re.match(pattern_info["pattern"], query_text, re.IGNORECASE):
            return pattern_info["response"]
    return None


# 非流式查询接口
@app.post("/api/query")
async def query(request: QueryRequest):
    start_time = time.time()  # 记录开始时间
    # 使用请求中的 session_id 或生成新 ID
    session_id = request.session_id or str(uuid.uuid4())
    # 检查是否为日常问候
    greeting_response = check_greeting(request.query)
    if greeting_response:
        # 返回问候回复
        return {
            "answer": greeting_response,
            "is_streaming": False,
            "session_id": session_id,
            "processing_time": time.time() - start_time
        }
    # 执行 BM25 搜索
    answer, need_rag = qa_system.bm25_search.search(request.query, threshold=0.85)
    if need_rag:
        # 需要 RAG，提示使用 WebSocket
        return {
            "answer": "请使用WebSocket接口获取流式响应",
            "is_streaming": True,
            "session_id": session_id,
            "processing_time": time.time() - start_time
        }
    # 返回 MySQL 答案
    return {
        "answer": answer,
        "is_streaming": False,
        "session_id": session_id,
        "processing_time": time.time() - start_time
    }

# 流式查询WebSocket接口
@app.websocket("/api/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()  # 接受 WebSocket 连接
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            request_data = json.loads(data)  # 解析 JSON 数据
            # 获取查询参数
            query = request_data.get("query")
            source_filter = request_data.get("source_filter")
            session_id = request_data.get("session_id", str(uuid.uuid4()))
            start_time = time.time()  # 记录开始时间
            # 发送开始标志
            if websocket.client_state == websocket.client_state.CONNECTED:
                await websocket.send_json({
                    "type": "start",
                    "session_id": session_id
                })
            # 检查是否为日常问候
            greeting_response = check_greeting(query)
            if greeting_response:
                # 问候也写入对话历史，与 RAG/BM25 回复保持一致，刷新后不丢
                try:
                    qa_system.update_session_history(session_id, query, greeting_response)
                except Exception as e:
                    logger.error(f"[ws] 问候历史写入失败: {e}")
                if websocket.client_state == websocket.client_state.CONNECTED:
                    # 发送问候回复
                    await websocket.send_json({
                        "type": "token",
                        "token": greeting_response,
                        "session_id": session_id
                    })
                    # 发送结束标志
                    await websocket.send_json({
                        "type": "end",
                        "session_id": session_id,
                        "is_complete": True,
                        "processing_time": time.time() - start_time
                    })
                break
            # 用 LangGraph 编排层流式处理查询。
            # 同步生成器在 worker 线程中步进，经 asyncio 队列回传事件循环，
            # 避免一个慢查询阻塞整棵事件循环（旧实现直接同步迭代会卡住其他客户端）。
            loop = asyncio.get_running_loop()
            out_q = asyncio.Queue()

            def _produce():
                try:
                    for item in qa_system.query_graph_stream(
                            query, source_filter=source_filter, session_id=session_id):
                        asyncio.run_coroutine_threadsafe(out_q.put(item), loop)
                except Exception as e:
                    # 生成中途异常也要保证发结束标志，避免前端永远等待
                    logger.error(f"[ws] 流式生成异常: {e}")
                    asyncio.run_coroutine_threadsafe(out_q.put(("", True, [])), loop)

            worker = threading.Thread(target=_produce, daemon=True)
            worker.start()

            # 最后一条 (is_complete=True) 的记录来源（引用溯源），用于 end 帧透出
            end_sources = []
            while True:
                token, is_complete, sources = await out_q.get()
                if sources:
                    end_sources = sources
                if token and websocket.client_state == websocket.client_state.CONNECTED:
                    # 发送 token 数据
                    await websocket.send_json({
                        "type": "token",
                        "token": token,
                        "session_id": session_id
                    })
                if is_complete:
                    if websocket.client_state == websocket.client_state.CONNECTED:
                        # 发送结束标志，携带引用溯源 sources
                        await websocket.send_json({
                            "type": "end",
                            "session_id": session_id,
                            "is_complete": True,
                            "processing_time": time.time() - start_time,
                            "sources": end_sources,
                        })
                    break
                await asyncio.sleep(0)  # 让出事件循环，token 到达即发送，无需人为节流
    except WebSocketDisconnect as e:
        # 记录 WebSocket 断开信息
        print(f"WebSocket disconnected: code={e.code}, reason={e.reason}")
    except Exception as e:
        # 记录错误信息
        print(f"WebSocket error: {str(e)}")
        if websocket.client_state == websocket.client_state.CONNECTED:
            # 发送错误消息
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
    finally:
        try:
            if websocket.client_state == websocket.client_state.CONNECTED:
                # 关闭 WebSocket 连接
                await websocket.close()
        except Exception as e:
            # 记录关闭连接时的错误
            print(f"Error closing WebSocket: {str(e)}")


# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# 获取有效的学科类别
@app.get("/api/sources")
async def get_sources():
    return {"sources": qa_system.config.VALID_SOURCES}

# 列出所有历史会话（供前端左栏会话列表切换）
@app.get("/api/sessions")
async def list_sessions():
    return {"sessions": qa_system.list_sessions()}


def _validate_subject(subject: Optional[str]) -> Optional[str]:
    """校验学科过滤参数，非法值抛 400，None 原样返回。"""
    if subject is None:
        return None
    if subject not in qa_system.config.VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"未知学科 '{subject}'，可选：{qa_system.config.VALID_SOURCES}")
    return subject


# ---- 知识库读接口（浏览 / 详情 / 库内搜索）----

@app.get("/api/kb/documents")
async def kb_list_documents(subject: Optional[str] = Query(None), q: Optional[str] = Query(None)):
    """知识库文档列表：按学科过滤 + 可选库内关键词过滤。"""
    subject = _validate_subject(subject)
    documents = qa_system.vector_store.list_documents(subject=subject, q=q)
    return {"documents": documents}


@app.get("/api/kb/documents/{doc_id}")
async def kb_get_document(doc_id: str):
    """单个文档详情（全文 + 有序切块）。"""
    detail = qa_system.vector_store.get_document(doc_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"文档 {doc_id} 不存在")
    return detail


@app.get("/api/kb/search")
async def kb_search(q: str = Query(...), subject: Optional[str] = Query(None)):
    """库内关键词搜索，按文档聚合返回命中摘要。"""
    subject = _validate_subject(subject)
    results = qa_system.vector_store.search_documents(q, subject=subject)
    return {"results": results}

# 静态资源：Vite 构建产物输出到 static/，base 用相对路径，assets/ 相对根目录解析。
# 必须放在最后挂载在 "/"，只兜底未匹配到的路径，避免吞掉上面 /api/* 与 WebSocket 路由。
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=False)