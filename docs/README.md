# AgenticGen 架构文档

本文档目录包含AgenticGen项目的完整架构设计文档。

## 📚 文档列表

### 1. [架构图文档](./architecture-diagrams.md)
包含以下主要架构图：
- 整体系统架构图
- 混合语言架构分层
- 微服务架构
- 数据流架构
- 智能体编排架构
- 安全架构
- 性能优化架构
- 部署架构

### 2. [模块架构文档](./module-architecture.md)
包含各核心功能模块的详细架构：
- 智能体管理模块
- 知识库模块
- 工具执行模块
- 实时协作模块
- 指标收集模块（Rust）
- 缓存引擎模块（Rust）
- 向量引擎模块（Rust）
- 编排引擎模块（Go）
- Python沙箱模块（Rust）
- 认证授权模块

## 🎯 架构特点

### 混合语言优势
- **Python**: AI/ML生态丰富（50K+库）
- **Go**: 高并发处理（10K+连接）
- **Rust**: 极致性能（1.5M ops/sec指标收集）

### 性能指标
- API响应时间：**73% 更快**（450ms → 120ms）
- 指标收集速率：**750x 提升**（2K → 1.5M ops/sec）
- 缓存操作：**52x 更快**（8K → 418K ops/sec）
- 向量计算：**300x 提升**（33 → 10K ops/sec）

### 架构优势
1. **高性能**：关键组件使用Rust实现极致性能
2. **高并发**：Go协程支持10K+并发连接
3. **高可用**：微服务架构，故障隔离
4. **易扩展**：模块化设计，水平扩展
5. **强安全**：完整的安全防护体系

## 🔍 快速导航

| 组件 | 语言 | 性能 | 文档链接 |
|------|------|---------|----------|
| 指标收集器 | Rust | **1.5M ops/sec** | [查看架构](./module-architecture.md#指标收集模块) |
| 缓存引擎 | Rust | **418K ops/sec** | [查看架构](./module-architecture.md#缓存引擎模块) |
| 向量引擎 | Rust | **10K ops/sec** | [查看架构](./module-architecture.md#向量引擎模块) |
| 编排引擎 | Go | **10K agents** | [查看架构](./module-architecture.md#编排引擎模块) |
| Python沙箱 | Rust | **<5% overhead** | [查看架构](./module-architecture.md#python沙箱模块) |
| 智能体管理 | Python | - | [查看架构](./module-architecture.md#智能体管理模块) |
| 知识库 | Python | - | [查看架构](./module-architecture.md#知识库模块) |

## 📖 使用说明

### 查看Mermaid图
所有架构图都使用Mermaid格式编写，支持在以下平台直接渲染：
- GitHub
- GitLab
- Notion
- Mermaid Live Editor

### 导出为图片
可以使用以下工具将Mermaid图导出为图片：
```bash
# 使用mermaid CLI
npm install -g @mermaid-js/mermaid-cli
mmdc -i input.mmd -o output.png

# 使用在线工具
# https://mermaid.live
```

## 🤝 贡献

如果您对架构设计有改进建议，请：
1. 创建Issue描述建议
2. 提交Pull Request
3. 参与架构讨论

## 📄 许可证

本文档遵循 [MIT License](../LICENSE)。

---

**注意**：本文档会随着项目发展持续更新。