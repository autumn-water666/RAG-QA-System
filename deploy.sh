#!/usr/bin/env bash
#
# deploy.sh —— 推送后一键部署
#
# 用法：每次推完代码，在仓库根目录跑：
#     bash deploy.sh
#
# 逻辑：
#   1. git pull 拉最新
#   2. 对比「上次部署」到 HEAD，判断前端/后端哪些有改动
#   3. 前端有改动 → npm build（产物进 static/，FastAPI 直接托管，刷新即"热更新"）
#   4. 后端有改动 → 按端口清理旧 uvicorn 进程并后台重启
#
# 不牵扯开机自启 / 系统服务，纯粹"推了就同步"。

set -e
cd "$(dirname "$0")/integrated_qa_system"
PROJ=$(pwd)
MARKER="$PROJ/.last_deploy"            # 记录上次部署到的 commit
PORT="${PORT:-8000}"                   # 后端端口，可 PORT=8080 bash deploy.sh 覆盖
LOG="$PROJ/logs/app.log"
mkdir -p "$PROJ/logs"

echo "==> 拉取最新代码"
git -C "$PROJ" pull --ff-only --prune

# 出上次部署点；首次运行则全部视为有改动
BASE="$(cat "$MARKER" 2>/dev/null || echo HEAD~1)"
HEAD="$(git -C "$PROJ" rev-parse HEAD)"
[ "$BASE" = "$HEAD" ] && { echo "没有新提交，head=$HEAD"; echo "（如只想强制重启/重建，先删 $MARKER）"; exit 0; }

FRONT_CHANGED=$(git -C "$PROJ" diff --name-only "$BASE" "$HEAD" -- frontend | grep -q . && echo 1 || echo 0)
BACK_CHANGED=$(git -C "$PROJ" diff --name-only "$BASE" "$HEAD" -- '*.py' | grep -q . && echo 1 || echo 0)

# ---- 前端：有改动就 build（产物进 static/，服务器托管，刷新即热更）----
if [ "$FRONT_CHANGED" = "1" ]; then
    echo "==> 前端有改动，构建中"
    ( cd "$PROJ/frontend" && npm ci >/dev/null && npm run build )
    echo "    构建完成 -> static/（浏览器刷新即可看到）"
else
    echo "--> 前端无改动，跳过构建"
fi

# ---- 后端：有改动就重启 uvicorn ----
if [ "$BACK_CHANGED" = "1" ]; then
    echo "==> 后端有改动，重启 uvicorn (:$PORT)"
    # 清掉占用该端口的进程（可能是旧 uvicorn）
    OLD_PID=$(netstat -ano 2>/dev/null | grep -E ":$PORT\\s" | grep LISTENING | awk '{print $5}' | head -1)
    if [ -n "$OLD_PID" ]; then
        kill "$OLD_PID" 2>/dev/null && echo "    已停旧进程 $OLD_PID" || taskkill //PID "$OLD_PID" //F >/dev/null 2>&1
        sleep 1
    fi
    # 后台起新进程，日志落 logs/app.log
    nohup python -m uvicorn app:app --host 0.0.0.0 --port "$PORT" >> "$LOG" 2>&1 &
    echo "    已后台启动（日志: logs/app.log）"
else
    echo "--> 后端无改动，跳过重启（已在跑的服务保持）"
fi

# 记录本次部署点
echo "$HEAD" > "$MARKER"
echo "==> 部署完成 @ $HEAD"

if [ "$BACK_CHANGED" = "1" ]; then
    echo "提示：后端刚重启，约需 15 秒加载模型后才可用；等待期间请求可能失败。"
    echo "    可用 PORT=$PORT 的 /health 轮询：curl http://localhost:$PORT/health"
fi