/**
 * 表现层 - Agent 会话页面
 *
 * 路由: /agents/:id/chat
 * 提供 ChatGPT 风格的对话体验。
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
import { TaskStatusPanel } from '@presentation/components/chat/TaskStatusPanel';

export const AgentSessionPage: React.FC = () => {
  const { id: agentId } = useParams<{ id: string }>();
  const navigate = useNavigate();

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
  const {
    isSending,
    isStreaming,
    currentPhase,
    currentTask,
    error: chatError,
    sendMessage,
    cancelExecution,
  } = useChat({
    agentId: agentId || '',
    sessionId: currentSession?.id || null,
    onAppendMessage: appendMessage,
    onUpsertMessage: upsertMessage,
    onUpdateMessageById: updateMessageById,
    onUpdateLastAssistant: updateLastAssistantMessage,
  });

  // 加载 Agent 和 Sessions
  useEffect(() => {
    if (!agentId) {
      navigate('/agents');
      return;
    }
    fetchAgent(agentId);
    fetchSessions();
  }, [agentId, fetchAgent, fetchSessions, navigate]);

  // 创建新会话
  const handleNewSession = useCallback(async () => {
    try {
      await createSession();
    } catch {
      // error handled by hook
    }
  }, [createSession]);

  // 选择会话
  const handleSelectSession = useCallback(async (sessionId: string) => {
    try {
      await selectSession(sessionId);
    } catch {
      // error handled by hook
    }
  }, [selectSession]);

  // 删除会话
  const handleDeleteSession = useCallback(async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
    } catch {
      // error handled by hook
    }
  }, [deleteSession]);

  // 发送消息（如果没有 session 则自动创建）
  const handleSendMessage = useCallback(async (content: string) => {
    if (!currentSession) {
      const session = await createSession();
      if (!session) return;
      // 等待 session 创建完成后，下一个 render 周期再发送
      // useChat 的 sessionId 依赖 currentSession，需要等待更新
      setTimeout(() => sendMessage(content), 50);
      return;
    }
    sendMessage(content);
  }, [currentSession, createSession, sendMessage]);

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
        />

        {/* 错误提示 */}
        {chatError && (
          <div className="mx-4 mt-2 rounded-lg border border-destructive bg-destructive/10 p-2 text-sm text-destructive">
            {chatError}
          </div>
        )}

        <TaskStatusPanel task={currentTask} />

        {/* 消息列表 */}
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onClarifyAnswer={handleSendMessage}
        />

        {/* 输入框 */}
        <MessageInput
          onSend={handleSendMessage}
          disabled={isSending || isStreaming}
          placeholder={
            !currentSession
              ? 'Send a message to start a new chat...'
              : 'Type a message...'
          }
        />
      </div>
    </div>
  );
};
