# Phase 3: UI & Deployment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 3-UI & Deployment
**Areas discussed:** API 接口组织方式, Streamlit 页面布局, 聊天体验

---

## API 接口组织方式

| Option | Description | Selected |
|--------|-------------|----------|
| 按资源拆分 | backend/api/documents.py, chat.py, search.py 各自独立文件 | ✓ |
| 单文件集中 | 所有路由写在一个 backend/main.py 里 | |

**User's choice:** 按资源拆分
**Notes:** 与 architecture.md 推荐的目录结构一致，便于后期维护。

---

| Option | Description | Selected |
|--------|-------------|----------|
| App 级单例 | FastAPI 启动时创建实例注册到 app.state | ✓ |
| 每次请求新建 | 每个请求创建 MetadataStore 连接 | |

**User's choice:** App 级单例
**Notes:** 与现有 get_instance() 单例模式一致。

---

| Option | Description | Selected |
|--------|-------------|----------|
| /api/v1/xxx | 统一前缀，预留版本空间 | ✓ |
| 直接 /xxx | 更短但后续升级困难 | |

**User's choice:** /api/v1/xxx
**Notes:** 统一版本前缀，后续支持 v2 等升级。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 全局异常处理器 | 自定义异常类 + @app.exception_handler | ✓ |
| 各路由自行处理 | 每个端点自己 try/except | |

**User's choice:** 全局异常处理器
**Notes:** 错误格式一致，减少重复代码。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 背景任务+状态轮询 | FastAPI BackgroundTasks + GET status 端点 | ✓ |
| 同步阻塞 | 索引结束再返回，大文档可能超时 | |

**User's choice:** 背景任务+状态轮询
**Notes:** 零额外依赖，满足 API-05 异步需求。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 统一包装 | {"status":"ok","data":...,"error":null} | ✓ |
| 直接返回 | 原始数据，错误格式需单独约定 | |

**User's choice:** 统一包装
**Notes:** 客户端解析一致。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 需要健康检查 | GET /api/v1/health，含依赖状态 | ✓ |
| 不需要 | 启动时检查，不做运行时检测 | |

**User's choice:** 需要健康检查
**Notes:** Docker 部署和监控场景都需要。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 开发宽松，生产收紧 | 开发允许 localhost，生产配置域名 | ✓ |
| 全程关闭 CORS | 用 nginx 反代统一端口 | |

**User's choice:** 开发宽松，生产收紧
**Notes:** FastAPI 的 CORSMiddleware 支持按环境配置。

---

## Streamlit 页面布局

| Option | Description | Selected |
|--------|-------------|----------|
| 三页结构 | 1_Documents.py, 2_Chat.py, 3_Preview.py | ✓ |
| 两页结构 | Document 合并上传/列表/预览，Chat 单独 | |
| 单页结构 | 所有功能一个页面，expander 分区 | |

**User's choice:** 三页结构
**Notes:** Streamlit 原生多页面，按数字排序。功能清晰分离。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 侧边栏 radio 切换 | st.sidebar.radio 切换页面 | ✓ |
| st.navigation 原生导航 | 新版 API，更美观但版本要求高 | |
| 顶部 Tabs | st.tabs 同页面切换视图 | |

**User's choice:** 侧边栏 radio 切换
**Notes:** Streamlit 最常见导航模式，用户一目了然。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 侧边栏下拉选择 | st.sidebar.selectbox 列出已索引文档 | ✓ |
| 文档列表页跳转 | st.switch_page 跳到聊天页传参 | |
| session_state 全局管理 | 各页面读写 selected_doc_id | |

**User's choice:** 侧边栏下拉选择
**Notes:** 全局可见，聊天和预览页面自动跟随切换。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 独立页面 | 单独页面显示 Article/Section 层级树 | ✓ |
| 嵌入聊天页侧边栏 | 聊天时边看结构边提问 | |
| 文档列表页 inline 展开 | expander 展开预览 | |

**User's choice:** 独立页面
**Notes:** 适合仔细阅读文档结构，不受空间限制。

---

## 聊天体验

| Option | Description | Selected |
|--------|-------------|----------|
| 多轮对话 | 保留历史记录，可追问 | ✓ |
| 单轮对话 | 每次提问独立，不保留上下文 | |

**User's choice:** 多轮对话
**Notes:** session_state 管理对话列表即可。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 流式输出 | 逐 token 显示，st.write_stream | ✓ |
| 非流式 | 全部生成完再展示 | |

**User's choice:** 流式输出
**Notes:** 现代 UI 体验，用户实时看到生成过程。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 可折叠面板展示 | st.expander 展示被引用 chunk 原文 | ✓ |
| 仅引用编号 | 只显示 [Article X, Section Y] | |
| 不展示来源 | 只显示答案 | |

**User's choice:** 可折叠面板展示
**Notes:** 法律 RAG 需要透明可验证，用户可以自行核对来源。

---

| Option | Description | Selected |
|--------|-------------|----------|
| 可点击展开原文 | 引用标记做成按钮，点击显示原文 | ✓ |
| 纯文本标记 | 引用只是文本 | |
| 底部引用面板 | 引用集中显示在答案底部 | |

**User's choice:** 可点击展开原文
**Notes:** 交互性强，用户可以直接点开查看引用的具体法律条文原文。

---

## Agent's Discretion

- Streamlit 组件实现细节（citation box 渲染、preview 树形展示）
- API 错误消息内容和样式
- CSS/styling 选择
- Docker 多阶段构建细节（如基础镜像选择）

## Deferred Ideas

None — discussion stayed within phase scope. All Phase 3 requirements are committed.
