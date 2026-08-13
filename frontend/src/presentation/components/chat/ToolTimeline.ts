/**
 * 表现层 - 工具时间线构建（纯函数）
 *
 * 将 tool_calls + tool_results 合并为按调用顺序排列的时间线项：
 * - 优先按调用 ID 精确匹配结果
 * - 无 ID 匹配时按工具名回退匹配
 * - 未被任何调用消费的结果追加到末尾
 */

import type { SessionMessage } from '@domain/entities/session';

type VisibleToolCall = SessionMessage['tool_calls'][number];
type VisibleToolResult = SessionMessage['tool_results'][number];

export interface ToolTimelineItem {
  key: string;
  name: string;
  status: string;
  result?: string;
  input?: Record<string, unknown>;
  args?: Record<string, unknown>;
  /** 仅 awaiting_confirmation：危险命令风险原因 */
  riskReason?: string;
}

const SPECIAL_TOOL_NAMES = new Set(['plan', 'plan_execute', 'plan_update', 'clarify']);

export const isSpecialTool = (toolName: string): boolean =>
  SPECIAL_TOOL_NAMES.has(toolName);

/**
 * 构建工具时间线。
 *
 * 用 Map<id, index[]> 预索引结果，将 ID 匹配从 O(n²) 降为接近 O(n)；
 * 仅无 ID 命中的调用才走按名称的线性回退（与旧实现语义一致）。
 */
export const buildToolTimeline = (
  calls: VisibleToolCall[],
  results: VisibleToolResult[],
): ToolTimelineItem[] => {
  const usedResultIndexes = new Set<number>();

  // 预索引：id → 结果下标（同 id 罕见，但按顺序入队）
  const resultsById = new Map<string, number[]>();
  results.forEach((result, resultIndex) => {
    if (!result.id) return;
    const indexes = resultsById.get(result.id);
    if (indexes) {
      indexes.push(resultIndex);
    } else {
      resultsById.set(result.id, [resultIndex]);
    }
  });

  const takeById = (id: string | undefined): number => {
    if (!id) return -1;
    const indexes = resultsById.get(id);
    if (!indexes) return -1;
    while (indexes.length > 0) {
      const candidate = indexes[0];
      if (!usedResultIndexes.has(candidate)) return candidate;
      indexes.shift();
    }
    return -1;
  };

  const takeByName = (name: string): number =>
    results.findIndex(
      (result, resultIndex) =>
        !usedResultIndexes.has(resultIndex) && result.tool_name === name,
    );

  const items: ToolTimelineItem[] = calls.map((call, index) => {
    const exactIndex = takeById(call.id);
    const fallbackIndex = exactIndex >= 0 ? exactIndex : takeByName(call.name);
    const result = fallbackIndex >= 0 ? results[fallbackIndex] : undefined;
    if (fallbackIndex >= 0) usedResultIndexes.add(fallbackIndex);

    return {
      key: call.id || `${call.name}-${index}`,
      name: call.name,
      status: result?.status || 'running',
      result: result?.result,
      input: call.input,
      args: call.args,
    };
  });

  // 未被消费的结果追加到末尾（保持原有展示语义）
  results.forEach((result, index) => {
    if (usedResultIndexes.has(index)) return;
    items.push({
      key: result.id || `${result.tool_name}-result-${index}`,
      name: result.tool_name,
      status: result.status || 'success',
      result: result.result,
    });
  });

  return items;
};
