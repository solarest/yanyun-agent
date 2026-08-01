/**
 * 表现层 - Agent 会话页面
 * 
 * 路由: /agents/:id/chat
 * 提供 ChatGPT 风格的对话体验，包含：
 * - 左侧会话列表
 * - 右侧聊天区域（消息列表 + 任务面板 + 输入框）
 */
import React, { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAgentManagement } from '@application/services/useAgentManagement';
import { useSessionService } from '@application/services/useSessionService';
import { useChat } from '@application/services/useChat';
import { SessionSidebar } from '@presentation/components/chat/SessionSidebar';
import { ChatHeader } from '@presentation/components/chat/ChatHeader';
import { MessageList } from '@presentation/components/chat/MessageList';
import { MessageInput } from '@presentation/components/chat/MessageInput';
import { TaskPanel } from '@presentation/components/chat';
import { SkillSelector } from '@presentation/components/chat/SkillSelector';

export const AgentSessionPage: React.FC = () => {
  const { id: agentId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [isRestoring, setIsRestoring] = React.useState(false);
  const [selectedSkillIds, setSelectedSkillIds] = React.useState<string[]>([]);

  // Agent 信息
  const { currentAgent, fetchAgent } = useAgentManagement();

  // Session 管理
  const {
    sessions,
    currentSession,
    messages,
    isLoading: isSessionLoading,
    fetchSessions,
    createSession,
    selectSession,
    deleteSession,
    appendMessage,
    upsertMessage,
    updateMessageById,
    updateLastAssistantMessage,
  } = useSessionService(agentId || '');

  // Chat 交互
  const getMessages = React.useCallback(() => messages, [messages]);

  const {
    isSending,
    isStreaming,
    isReplaying,
    currentPhase,
    currentTask,
    currentTaskId,
    error: chatError,
    sendMessage,
    cancelExecution,
    replayStream,
  } = useChat({
    agentId: agentId || '',
    sessionId: currentSession?.id || null,
    onAppendMessage: appendMessage,
    onUpsertMessage: upsertMessage,
    onUpdateMessageById: updateMessageById,
    onUpdateLastAssistant: updateLastAssistantMessage,
    onSessionUpdated: fetchSessions, // 刷新会话列表以获取最新标题
    getMessages,
  });

  // 手动触发 SSE 重放
  const handleReplay = useCallback(() => {
    // 优先级: currentTaskId > 最后一条 assistant 消息的 task_id > localStorage
    const assistantMessages = messages.filter(m => m.role === 'assistant');
    const lastAssistantMsg = assistantMessages.pop();
    let taskId = currentTaskId || lastAssistantMsg?.task_id;

    // Fallback: 从 localStorage 读取
    if (!taskId) {
      try {
        const raw = localStorage.getItem('activeTaskState');
        if (raw) {
          const state = JSON.parse(raw);
          if (state.agentId === agentId) {
            taskId = state.taskId;
          }
        }
      } catch {
        // ignore
      }
    }

    console.log('[AgentSessionPage] Replay debug:', {
      currentTaskId, lastAssistantTaskId: lastAssistantMsg?.task_id,
      finalTaskId: taskId, messagesCount: messages.length,
    });

    if (taskId) {
      console.log('[AgentSessionPage] Replaying task:', taskId);
      replayStream(true, taskId);
    } else {
      console.warn('[AgentSessionPage] No task to replay');
    }
  }, [currentTaskId, messages, replayStream, agentId]);

  // 初始化：加载 Agent 信息和会话列表
  useEffect(() => {
    if (!agentId) {
      navigate('/agents');
      return;
    }
    fetchAgent(agentId);
    fetchSessions();
  }, [agentId, fetchAgent, fetchSessions, navigate]);

  // 检测活动任务恢复状态 (useChat 内部通过 API + localStorage 自动恢复)
  useEffect(() => {
    if (isReplaying) {
      setIsRestoring(true);
      // 当第一条消息被追加时，认为恢复完成
      const checkRestored = setInterval(() => {
        if (messages.length > 0) {
          setIsRestoring(false);
          clearInterval(checkRestored);
        }
      }, 500);
      // 最多 10 秒后自动关闭提示
      setTimeout(() => {
        setIsRestoring(false);
        clearInterval(checkRestored);
      }, 10000);
      return () => clearInterval(checkRestored);
    }
  }, [isReplaying, messages.length]);

  // 创建新会话
  const handleNewSession = useCallback(async () => {
    await createSession();
  }, [createSession]);

  // 选择会话
  const handleSelectSession = useCallback(async (sessionId: string) => {
    await selectSession(sessionId);
  }, [selectSession]);

  // 删除会话
  const handleDeleteSession = useCallback(async (sessionId: string) => {
    await deleteSession(sessionId);
  }, [deleteSession]);

  // 发送消息（无 session 时自动创建）
  const handleSendMessage = useCallback(async (content: string) => {
    const skillOpts = selectedSkillIds.length > 0 ? { skill_ids: selectedSkillIds } : {};
    if (!currentSession) {
      const session = await createSession();
      if (!session) return;
      // 显式传入 session.id，避免等待 currentSession 闭包刷新导致的首条消息丢失
      sendMessage(content, skillOpts, session.id);
      return;
    }
    sendMessage(content, skillOpts);
  }, [currentSession, createSession, sendMessage, selectedSkillIds]);

  // 自动恢复上次活跃的 session（页面刷新后从 localStorage 读取）
  useEffect(() => {
    if (!agentId || sessions.length === 0 || currentSession) return;
    try {
      const raw = localStorage.getItem('activeTaskState');
      if (!raw) return;
      const state = JSON.parse(raw);
      if (state.agentId === agentId && state.sessionId) {
        const targetSession = sessions.find(s => s.id === state.sessionId);
        if (targetSession) {
          console.log('[AgentSessionPage] Auto-restoring session:', state.sessionId);
          handleSelectSession(state.sessionId);
        }
      }
    } catch {
      // ignore
    }
  }, [agentId, sessions, currentSession, handleSelectSession]);

  if (!agentId) return null;

  return (
    <div className="flex h-screen">
      {/* 左侧会话列表 */}
      <SessionSidebar
        sessions={sessions}
        currentSessionId={currentSession?.id || null}
        isLoading={isSessionLoading}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* 右侧聊天区域 */}
      <div className="flex flex-1 flex-col">
        <ChatHeader
          agentName={currentAgent?.name || 'Agent'}
          agentId={agentId}
          session={currentSession}
          isStreaming={isStreaming}
          currentPhase={currentPhase}
          onCancel={cancelExecution}
          onReplay={handleReplay}
          isReplaying={isReplaying}
          canReplay={!isStreaming && messages.length > 0}
        />

        {/* 恢复状态提示 */}
        {isRestoring && (
          <div className="mx-4 mt-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-sm text-blue-700">
            正在恢复会话状态...
          </div>
        )}

        {/* 错误提示 */}
        {chatError && (
          <div className="mx-4 mt-2 rounded-lg border border-destructive bg-destructive/10 p-2 text-sm text-destructive">
            {chatError}
          </div>
        )}

        {/* 消息列表 */}
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onClarifyAnswer={handleSendMessage}
        />

        {/* 任务列表面板 */}
        <TaskPanel task={currentTask} />

        {/* 输入框（含左侧 "+" 技能选择按钮） */}
        <MessageInput
          onSend={handleSendMessage}
          disabled={isSending || isStreaming}
          placeholder={
            !currentSession
              ? '发送消息开始新对话...'
              : '输入消息...'
          }
          leftActions={
            <SkillSelector
              selectedSkillIds={selectedSkillIds}
              onSelectionChange={setSelectedSkillIds}
            />
          }
        />
      </div>
    </div>
  );
};
