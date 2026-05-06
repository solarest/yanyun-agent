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
    onSessionUpdated: fetchSessions, // 刷新会话列表以获取最新标题
  });

  // 初始化：加载 Agent 信息和会话列表
  useEffect(() => {
    if (!agentId) {
      navigate('/agents');
      return;
    }
    fetchAgent(agentId);
    fetchSessions();
  }, [agentId, fetchAgent, fetchSessions, navigate]);

  // 检测是否有活动任务需要恢复
  useEffect(() => {
    const savedTaskId = sessionStorage.getItem('activeTaskId');
    const savedSessionId = sessionStorage.getItem('activeSessionId');
    const timestamp = sessionStorage.getItem('taskStateTimestamp');

    if (savedTaskId && savedSessionId && timestamp) {
      // 检查是否在5分钟内
      if (Date.now() - parseInt(timestamp) < 5 * 60 * 1000) {
        setIsRestoring(true);
        // 当第一条消息被追加时,认为恢复完成
        const checkRestored = setInterval(() => {
          if (messages.length > 0) {
            setIsRestoring(false);
            clearInterval(checkRestored);
          }
        }, 500);
        // 最多5秒后自动关闭提示
        setTimeout(() => {
          setIsRestoring(false);
          clearInterval(checkRestored);
        }, 5000);
        return () => clearInterval(checkRestored);
      }
    }
  }, [messages.length]);

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
      // 等待 session 创建完成后发送（useChat 依赖 currentSession）
      setTimeout(() => sendMessage(content, skillOpts), 50);
      return;
    }
    sendMessage(content, skillOpts);
  }, [currentSession, createSession, sendMessage, selectedSkillIds]);

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
