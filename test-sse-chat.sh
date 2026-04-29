#!/bin/bash
# SSE Chat 链路测试脚本

echo "=== SSE Chat 链路验证 ==="
echo ""

# 配置
AGENT_ID="75115daf-036c-4cc8-b26d-0e6e545143fa"
SESSION_ID="f96b0808-49ee-4d99-b6a1-7356db0a5668"
BACKEND_URL="http://localhost:8000"

echo "1. 发送消息..."
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/agents/$AGENT_ID/sessions/$SESSION_ID/messages" \
  -H "Content-Type: application/json" \
  -d '{"content": "你好，请简单回复测试"}')

TASK_ID=$(echo $RESPONSE | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TASK_ID" ]; then
  echo "❌ 失败：未获取到 task_id"
  echo "响应: $RESPONSE"
  exit 1
fi

echo "✅ 消息发送成功，task_id: $TASK_ID"
echo ""

echo "2. 等待 1 秒让任务开始执行..."
sleep 1

echo "3. 连接 SSE 流（超时 10 秒）..."
echo "---"

# 使用 curl 连接 SSE，10秒后自动断开
curl -N -m 10 "$BACKEND_URL/api/tasks/$TASK_ID/stream" 2>/dev/null | while read -r line; do
  if [[ $line == event:* ]]; then
    EVENT=$(echo $line | cut -d' ' -f2)
    echo "📨 收到事件: $EVENT"
  elif [[ $line == data:* ]]; then
    # 提取关键信息
    if echo $line | grep -q "llm-chunk"; then
      TEXT=$(echo $line | grep -o '"text":"[^"]*"' | cut -d'"' -f4)
      echo "  └─ Chunk: $TEXT"
    elif echo $line | grep -q "llm-complete"; then
      FULL_TEXT=$(echo $line | grep -o '"fullText":"[^"]*"' | cut -d'"' -f4)
      echo "  └─ Complete: $FULL_TEXT"
    elif echo $line | grep -q "task-completed"; then
      echo "  └─ ✅ 任务完成"
    fi
  fi
done

echo ""
echo "=== 测试完成 ==="
