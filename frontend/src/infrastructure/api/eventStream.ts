/**
 * 基础设施层 - Agent SSE 事件流客户端
 *
 * 封装 EventSource，提供：
 * - 类型安全的事件监听（基于 AgentEventMap）
 * - 自动重连（指数退避）
 * - 断线补发（last-event-id）
 * - 事件 ID 去重（后端回放 + 实时流可能重复）
 */

import type { AgentEventMap, AgentEventName } from '@domain/entities/events';
import { SSE_EVENT_TYPES } from '@domain/entities/events';

/** 后端 SSE 事件统一信封 */
export interface SSEEvent<T = Record<string, unknown>> {
  id: string;
  event_type: string;
  data: T & { taskId: string };
  timestamp: string;
}

/** 强类型事件回调 */
export type EventCallback<K extends AgentEventName> = (data: AgentEventMap[K]) => void;

/**
 * Agent 事件流客户端
 */
export class AgentEventStream {
  private es: EventSource | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  // 统一存储为宽松类型；在 on/emit 处做类型收窄
  private handlers = new Map<string, Set<(data: unknown) => void>>();
  private processedEventIds = new Set<string>();

  constructor(
    private baseUrl: string,
    private taskId: string,
  ) {}

  /**
   * 连接到 SSE 事件流
   */
  connect(): void {
    const url = `${this.baseUrl}/api/tasks/${this.taskId}/stream`;
    this.es = new EventSource(url);

    for (const type of SSE_EVENT_TYPES) {
      this.es.addEventListener(type, this.handleEvent);
    }
    this.es.addEventListener('error', this.handleError);
  }

  /**
   * 注册事件监听器
   * @returns 取消订阅函数
   */
  on<K extends AgentEventName>(eventType: K, handler: EventCallback<K>): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler as (data: unknown) => void);
    return () => {
      this.handlers.get(eventType)?.delete(handler as (data: unknown) => void);
    };
  }

  /**
   * 断开连接并清理资源
   */
  disconnect(): void {
    this.es?.close();
    this.es = null;
    this.handlers.clear();
    this.processedEventIds.clear();
    this.reconnectAttempts = 0;
  }

  private handleEvent = (e: MessageEvent): void => {
    let evt: SSEEvent;
    try {
      evt = JSON.parse(e.data) as SSEEvent;
    } catch (err) {
      console.error('[EventStream] Failed to parse SSE data:', err);
      return;
    }

    // 去重
    if (this.processedEventIds.has(evt.id)) return;
    this.processedEventIds.add(evt.id);

    // 将 SSE 协议层事件名（连字符）转换为内部格式（冒号）
    const eventType = evt.event_type.replace(/-/g, ':');
    this.dispatch(eventType, evt.data);
  };

  private dispatch(eventType: string, payload: unknown): void {
    this.handlers.get(eventType)?.forEach((h) => {
      try {
        h(payload);
      } catch (err) {
        console.error(`[EventStream] Handler for ${eventType} threw:`, err);
      }
    });
  }

  private handleError = (): void => {
    // EventSource 自带重连机制；仅在连接彻底关闭时介入
    if (this.es?.readyState === EventSource.CLOSED) {
      this.reconnectAttempts++;
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        console.warn(`[EventStream] Reconnecting in ${delay}ms...`);
        setTimeout(() => this.connect(), delay);
      } else {
        console.error('[EventStream] Max reconnect attempts reached');
        this.dispatch('task:failed', { taskId: this.taskId, error: 'Connection lost' });
      }
    }
  };
}
