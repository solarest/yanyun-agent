/**
 * 应用层 - Agent 配置自动生成 Hook
 */

/** Vibe 映射表 */
const VIBE_MAP: Record<
  string,
  { trait: string; style: string; quote: string }
> = {
  Professional: {
    trait: '严谨、专业、可靠',
    style: '正式、准确、逻辑清晰',
    quote: '专业成就卓越',
  },
  Friendly: {
    trait: '温暖、亲切、耐心',
    style: '友好、鼓励、平易近人',
    quote: '用微笑服务每一位',
  },
  Creative: {
    trait: '创新、灵活、富有想象',
    style: '生动、有趣、启发式',
    quote: '创意无限，想象无界',
  },
  Concise: {
    trait: '直接、高效、精简',
    style: '简洁、要点明确',
    quote: '少即是多',
  },
  Casual: {
    trait: '轻松、随和、幽默',
    style: '口语化、幽默',
    quote: '工作也可以很有趣',
  },
  Expert: {
    trait: '权威、深入、全面',
    style: '专业术语、详细解释',
    quote: '知识就是力量',
  },
};

/** Vibe 选项列表 */
export const VIBE_OPTIONS = Object.keys(VIBE_MAP);

/** Vibe 中文标签 */
export const VIBE_LABELS: Record<string, string> = {
  Professional: '专业严谨',
  Friendly: '友好亲切',
  Creative: '创意丰富',
  Concise: '简洁直接',
  Casual: '轻松随意',
  Expert: '专家权威',
};

export interface GenerationInput {
  name: string;
  description: string;
  vibes: string[];
}

export interface GeneratedContent {
  identity_md: string;
  soul_md: string;
  agents_md: string;
  bootstrap_md: string;
  memory_md: string;
  tools_md: string;
  user_md: string;
}

function generateIdentityMd(input: GenerationInput): string {
  return `# ${input.name}

## 身份
你是 ${input.name}，${input.description}。

## 边界
- 不提供超出能力范围的服务
- 不存储或泄露用户隐私信息
- 遵守安全规范和法律法规

## 版本
- v1.0.0`;
}

function generateSoulMd(input: GenerationInput): string {
  if (input.vibes.length === 0) {
    return `# 人格定义

## 性格特征
友好、专业

## 语言风格
清晰、准确

## 座右铭
"用心服务"`;
  }

  const vibeTraits = input.vibes
    .map((v) => VIBE_MAP[v]?.trait ?? v)
    .join('、');
  const vibeStyle = input.vibes
    .map((v) => VIBE_MAP[v]?.style ?? v)
    .join('、');
  const quote = VIBE_MAP[input.vibes[0]]?.quote ?? '用心服务';

  return `# 人格定义

## 性格特征
${vibeTraits}

## 语言风格
${vibeStyle}

## 座右铭
"${quote}"`;
}

function generateAgentsMd(_input: GenerationInput): string {
  return `# 调度规则与标准作业程序

## 任务处理流程
1. 接收用户请求
2. 分析任务类型和优先级
3. 按能力范围执行任务
4. 返回结构化结果

## 决策规则
- 遇到不确定的需求时，主动澄清
- 涉及高风险操作时，请求用户确认`;
}

function generateBootstrapMd(_input: GenerationInput): string {
  return `# 初始化配置

## 系统约束
- 遵守安全边界，不执行危险操作
- 保护用户隐私，不泄露敏感信息

## 格式要求
- 使用 Markdown 格式输出
- 代码块使用语法高亮`;
}

function generateToolsMd(_input: GenerationInput): string {
  return `# 工具授权

## 可用工具
（待在 Tools 配置步骤中设定）

## 调用约束
- 遵守工具调用频率限制
- 高风险工具需用户确认后执行`;
}

function generateUserMd(input: GenerationInput): string {
  return `# 用户画像

## 目标用户
使用 ${input.name} 的用户

## 交互偏好
- 语言：中文
- 详细程度：适中`;
}

export const useAgentGenerator = () => {
  const generate = (input: GenerationInput): GeneratedContent => {
    return {
      identity_md: generateIdentityMd(input),
      soul_md: generateSoulMd(input),
      agents_md: generateAgentsMd(input),
      bootstrap_md: generateBootstrapMd(input),
      memory_md: '',
      tools_md: generateToolsMd(input),
      user_md: generateUserMd(input),
    };
  };

  return { generate, VIBE_MAP };
};
