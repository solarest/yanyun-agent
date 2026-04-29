/**
 * 基础设施层 - Agent SSE 事件流客户端
 *
 * 封装 EventSource，提供：
 * - 类型安全的事件监听
 * - 自动重连（指数退避）
 * - 断线补发（last-event-id）
 */

export interface SSEEvent {
  id: string;
  event_type: string;
  data: Record<string, unknown> & { taskId: string };
  timestamp: string;
}

export type EventCallback = (data: Record<string, unknown>) => void;

/**
 * Agent 事件流客户端
 */
export class AgentEventStream {
  private es: EventSource | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private handlers = new Map<string, Set<EventCallback>>();
  private processedEventIds = new Set<string>();

  constructor(
    private baseUrl: string,
    private taskId: string
  ) {}

  /**
   * 连接到 SSE 事件流
   */
  connect(): void {
    const url = `${this.baseUrl}/api/tasks/${this.taskId}/stream`;
    this.es = new EventSource(url);

    // 注册所有事件监听器
    const eventTypes = [
      'task-started', 'task-completed', 'task-failed', 'task-cancelled',
      'phase-changed',
      'llm-chunk', 'llm-complete',
      'loop-detected',
      'tool-call', 'tool-security-check', 'tool-approval-request', 'tool-result',
      'context-compacting',
      'cost-update',
      'session-message-saved',
    ];

    for (const type of eventTypes) {
      this.es.addEventListener(type, this.handleEvent.bind(this));
    }

    // 错误处理 + 自动重连
    this.es.addEventListener('error', this.handleError.bind(this));
  }

  /**
   * 注册事件监听器
   * @returns 取消订阅函数
   */
  on(eventType: string, handler: EventCallback): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);
    return () => { this.handlers.get(eventType)?.delete(handler); };
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.es?.close();
    this.es = null;
    this.handlers.clear();
  }

  private handleEvent(e: MessageEvent): void {
    const data = JSON.parse(e.data) as SSEEvent;
    // 去重：跳过已处理的事件（后端回放 + 实时可能重复）
    if (this.processedEventIds.has(data.id)) {
      return;
    }
    this.processedEventIds.add(data.id);
    // 将 SSE 事件名（连字符）转回内部格式（冒号）
    const eventType = data.event_type.replace(/-/g, ':');
    this.emit(eventType, data.data);
  }

  private emit(eventType: string, payload: Record<string, unknown>): void {
    this.handlers.get(eventType)?.forEach(h => h(payload));
  }

  private handleError(): void {
    this.reconnectAttempts++;
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      console.log(`[EventStream] Reconnecting in ${delay}ms...`);
      setTimeout(() => this.connect(), delay);
    } else {
      console.error('[EventStream] Max reconnect attempts reached');
      this.emit('task:failed', { error: 'Connection lost' });
    }
  }
}
