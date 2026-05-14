/**
 * 基础设施层 - Agent SSE 事件流客户端
 *
 * 封装 EventSource，提供：
 * - 类型安全的事件监听（基于 AgentEventMap）
 * - 自动重连（指数退避）
 * - 断线补发（last-event-id）
 * - 事件 ID 去重（后端回放 + 实时流可能重复）
 * - 重放模式：事件入队后按固定间隔逐个分发，模拟流式体验
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

/** 事件队列项 */
interface QueuedEvent {
  eventType: string;
  payload: unknown;
}

/** 默认重放间隔（毫秒） */
const DEFAULT_REPLAY_INTERVAL_MS = 50;

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

  // 重放模式相关
  private replayMode = false;
  private replayIntervalMs = DEFAULT_REPLAY_INTERVAL_MS;
  private eventQueue: QueuedEvent[] = [];
  private drainTimer: ReturnType<typeof setTimeout> | null = null;
  private isDraining = false;

  constructor(
    private baseUrl: string,
    private taskId: string,
  ) {}

  /**
   * 启用重放模式：事件不会立即分发，而是入队后按固定间隔逐个消费
   */
  enableReplayMode(intervalMs = DEFAULT_REPLAY_INTERVAL_MS): void {
    this.replayMode = true;
    this.replayIntervalMs = intervalMs;
  }

  /**
   * 连接到 SSE 事件流
   */
  connect(): void {
    this.es?.close();
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
    this.stopDrain();
    this.eventQueue = [];
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
    this.reconnectAttempts = 0;

    const rawEventType =
      (typeof evt.event_type === 'string' && evt.event_type) || e.type;
    const eventType = this.normalizeEventType(rawEventType);

    if (this.replayMode) {
      this.eventQueue.push({ eventType, payload: evt.data });
      this.scheduleDrain();
    } else {
      this.dispatch(eventType, evt.data);
    }
  };

  private normalizeEventType(eventType: string): string {
    if (eventType.includes(':')) {
      return eventType;
    }
    return eventType.replace(/-/g, ':');
  }

  private dispatch(eventType: string, payload: unknown): void {
    this.handlers.get(eventType)?.forEach((h) => {
      try {
        h(payload);
      } catch (err) {
        console.error(`[EventStream] Handler for ${eventType} threw:`, err);
      }
    });
  }

  /**
   * 启动队列消费：按固定间隔逐个分发事件
   */
  private scheduleDrain(): void {
    if (this.isDraining) return;
    this.isDraining = true;
    this.drainNext();
  }

  private drainNext(): void {
    const item = this.eventQueue.shift();
    if (!item) {
      this.isDraining = false;
      return;
    }
    this.dispatch(item.eventType, item.payload);
    this.drainTimer = setTimeout(() => this.drainNext(), this.replayIntervalMs);
  }

  private stopDrain(): void {
    if (this.drainTimer !== null) {
      clearTimeout(this.drainTimer);
      this.drainTimer = null;
    }
    this.isDraining = false;
  }

  private handleError = (): void => {
    // EventSource 自带重连机制；仅在连接彻底关闭时介入
    if (this.es?.readyState === EventSource.CLOSED) {
      this.reconnectAttempts++;
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        console.warn(`[EventStream] Reconnecting in ${delay}ms...`);
        this.es.close();
        this.es = null;
        setTimeout(() => this.connect(), delay);
      } else {
        console.error('[EventStream] Max reconnect attempts reached');
        this.dispatch('task:failed', { taskId: this.taskId, error: 'Connection lost' });
      }
    }
  };
}
