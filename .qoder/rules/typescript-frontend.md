---
trigger: glob
glob: frontend/src/**/*.{ts,tsx}
---
# TypeScript 前端代码规范

## 类型
指定文件生效：frontend/src/**/*.{ts,tsx}

## 描述
前端 TypeScript 和 React 代码必须遵循的编码规范和最佳实践。

## 规则内容

### TypeScript 规范

1. **严格模式**
   - 启用 `strict: true`
   - 禁止使用 `any` 类型
   - 所有变量、参数、返回值必须有类型

```typescript
// 正确
const userName: string = 'John';
function getUser(id: number): User | null {
  // ...
}

// 错误
const userName = 'John'; // 缺少显式类型
function getUser(id: any): any {
  // ...
}
```

2. **类型定义位置**
   - 领域类型定义在 `domain/entities/`
   - 接口定义在 `domain/repositories/`
   - 组件 Props 定义在组件文件中

3. **使用 Interface 还是 Type**
   - 对象形状优先使用 `interface`
   - 联合类型、交叉类型使用 `type`

```typescript
// 对象形状
interface User {
  id: string;
  name: string;
  email: string;
}

// 联合类型
type UserRole = 'admin' | 'user' | 'guest';
type UserStatus = 'active' | 'inactive' | 'suspended';
```

### React 组件规范

1. **函数组件**
   - 使用函数组件，不使用类组件
   - 使用箭头函数定义

```typescript
// 正确
export const UserCard: React.FC<UserCardProps> = ({ user, onClick }) => {
  return (
    <div onClick={() => onClick(user.id)}>
      <h3>{user.name}</h3>
      <p>{user.email}</p>
    </div>
  );
};
```

2. **文件命名**
   - 组件文件：PascalCase（如 `UserCard.tsx`）
   - 工具文件：camelCase（如 `apiClient.ts`）
   - 测试文件：与源文件同名加 `.test`（如 `UserCard.test.tsx`）

3. **组件结构**
   - 每个组件单独一个文件
   - Props 接口定义在组件上方
   - 导出组件放在文件底部

```typescript
import React from 'react';
import { User } from '../../domain/entities';

interface UserCardProps {
  user: User;
  onClick: (userId: string) => void;
}

export const UserCard: React.FC<UserCardProps> = ({ user, onClick }) => {
  // 组件逻辑
  return (
    <div>{user.name}</div>
  );
};
```

### Hooks 规范

1. **自定义 Hooks**
   - 命名以 `use` 开头
   - 放在 `application/services/`
   - 返回明确的数据结构

```typescript
// 正确
export const useUserService = () => {
  const [users, setUsers] = useState<User[]>([]);
  
  const fetchUsers = async () => {
    const data = await userServiceApi.getAll();
    setUsers(data);
  };
  
  return { users, fetchUsers };
};
```

2. **Hooks 使用规则**
   - 只在组件顶层调用 Hooks
   - 只在 React 函数中调用 Hooks
   - 使用 ESLint 的 `react-hooks/rules-of-hooks` 检查

### API 调用规范

1. **API 客户端位置**
   - 所有 API 调用必须在 `infrastructure/api/` 中实现
   - 不要在组件中直接调用 axios/fetch

```typescript
// infrastructure/api/userApi.ts
import { apiClient } from './client';
import { User } from '../../domain/entities';

export const userServiceApi = {
  getAll: async (): Promise<User[]> => {
    const response = await apiClient.get('/users');
    return response.data;
  },
  
  getById: async (id: string): Promise<User> => {
    const response = await apiClient.get(`/users/${id}`);
    return response.data;
  },
};
```

2. **错误处理**
   - 在 API 层统一处理网络错误
   - 抛出有意义的错误信息
   - 在组件层显示用户友好的错误提示

```typescript
// 正确
try {
  const users = await userServiceApi.getAll();
} catch (error) {
  if (axios.isAxiosError(error)) {
    // 显示用户友好的错误信息
    showError('获取用户列表失败，请稍后重试');
  }
}
```

### 状态管理

1. **本地状态**
   - 使用 `useState` 和 `useReducer`
   - 状态尽量靠近使用它的组件

2. **服务端状态**
   - API 数据通过 application 层管理
   - 考虑使用 React Query 或 SWR（如果项目使用）

3. **全局状态**
   - 仅在多个组件需要共享时使用 Context
   - 避免过度使用全局状态

### 样式规范

1. **CSS 类命名**
   - 使用 BEM 或 CSS Modules
   - 避免内联样式

2. **响应式设计**
   - 使用 CSS 媒体查询
   - 移动优先设计

### 文件组织

```
frontend/src/
├── domain/
│   ├── entities/        # 领域类型定义
│   └── repositories/    # Repository 接口
├── application/
│   └── services/        # 应用服务（Hooks）
├── infrastructure/
│   ├── api/            # API 客户端
│   └── config/         # 配置
└── presentation/
    ├── components/     # React 组件
    └── pages/          # 页面组件
```

### 测试规范

1. **测试文件位置**
   - 与源文件放在一起或放在 `tests/` 目录
   - 命名：`ComponentName.test.tsx`

2. **测试类型**
   - 单元测试：测试单个函数/组件
   - 集成测试：测试组件交互
   - E2E 测试：测试完整用户流程

3. **测试工具**
   - Jest 或 Vitest
   - React Testing Library

```typescript
import { render, screen } from '@testing-library/react';
import { UserCard } from './UserCard';

describe('UserCard', () => {
  it('should display user name and email', () => {
    const user = { id: '1', name: 'John', email: 'john@example.com' };
    
    render(<UserCard user={user} onClick={() => {}} />);
    
    expect(screen.getByText('John')).toBeInTheDocument();
    expect(screen.getByText('john@example.com')).toBeInTheDocument();
  });
});
```

### 代码质量检查

提交前必须通过：

```bash
# 类型检查
npm run type-check

# 构建检查
npm run build

# 如果有 lint 脚本
npm run lint
```

### 性能优化

1. **组件优化**
   - 使用 `React.memo` 优化不必要的重渲染
   - 使用 `useMemo` 和 `useCallback` 缓存计算结果和函数

2. **代码分割**
   - 使用 `React.lazy` 和 `Suspense`
   - 路由级别代码分割

3. **避免的性能问题**
   - 不要在 render 中创建新对象/数组
   - 避免深层组件嵌套
   - 使用虚拟列表渲染大量数据
