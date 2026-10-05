# AI 学习助手

基于 PDF 的智能学习系统，支持知识点提取、知识可视化、学习规划、出题测试和智能问答。

## 功能特性

- 📄 **PDF 上传解析** - 上传 PDF 文档，自动提取文字、识别章节、文本分块
- 🧠 **知识点生成** - AI 自动提取知识点，构建知识层级结构
- 🌳 **思维导图** - 可视化展示知识点层级关系（D3.js）
- 🔗 **知识图谱** - 展示知识点之间的关联关系（vis.js）
- 📅 **学习规划** - AI 生成个性化学习计划
- ✍️ **测试练习** - 自动生成选择题、判断题、填空题
- 💬 **智能问答** - 基于 PDF 内容的 RAG 问答，带来源页码引用

## 技术栈

- **后端**: FastAPI + SQLAlchemy + SQLite
- **前端**: 原生 HTML/CSS/JavaScript
- **AI**: OpenAI 兼容接口（支持 OpenAI、DeepSeek 等）
- **PDF 解析**: PyMuPDF
- **可视化**: D3.js + vis.js

## 项目结构

```
ai-study-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 应用入口（lifespan 启动钩子）
│   │   ├── config.py        # 配置管理（路径基于 backend/ 解析为绝对路径）
│   │   ├── database.py      # 数据库连接（SQLAlchemy create_all 建表）
│   │   ├── models/          # 数据模型
│   │   ├── schemas/         # Pydantic 数据验证
│   │   ├── routers/         # API 路由（含统一进度端点 progress.py）
│   │   └── services/        # 业务逻辑（含 progress.py 进度注册表）
│   ├── scripts/smoke_test.py  # 冒烟自检（不需要 AI Key）
│   ├── uploads/             # PDF 文件存储（不入库）
│   ├── requirements.txt
│   └── .env.example         # 配置模板（真正的 .env 不入库）
├── frontend/
│   ├── index.html
│   ├── assets/vendor/       # d3 / vis-network 本地副本（离线可用）
│   ├── css/style.css
│   └── js/
│       ├── api.js           # API 封装
│       ├── progress.js      # 统一的真实进度条组件
│       ├── app.js           # 主应用逻辑
│       ├── knowledge.js     # 知识体系模块
│       ├── study-plan.js    # 学习规划模块
│       ├── quiz.js          # 测试模块
│       ├── qa.js            # 问答模块
│       ├── settings.js      # AI 设置弹窗
│       └── visualization.js # 可视化模块
├── docs/STATUS.md           # 现状梳理：依赖 / 仓库卫生 / 隐患清单
├── start.sh                 # 启动脚本
└── README.md
```

> 建表方式说明：项目使用 SQLAlchemy 的 `Base.metadata.create_all()` 建表，**没有接入 Alembic 迁移**（架构早期设想的 Alembic 未落地，依赖也已移除）。改表结构时请注意这一点。

## 快速开始

### 1. 安装依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动后端

推荐用启动脚本（在项目根目录）：

```bash
./start.sh          # 启动，默认 8000 端口
./start.sh 8001     # 指定端口启动
./start.sh stop     # 停止服务
```

脚本会自动检查虚拟环境和端口占用，并轮询 `/health` 确认真正就绪后才返回。
日志输出到 `backend/uvicorn.log`。

也可以手动启动：

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 配置 AI API

打开浏览器访问 `http://localhost:8000`，首次访问会自动弹出 AI 设置窗口。

或者点击左下角的 **⚙️ AI 设置** 按钮进行配置：

- **API 地址**：填入你的 AI 服务商 API 地址
- **API Key**：填入你的 API Key
- **模型**：选择或输入模型名称

支持的服务商：
| 服务商 | API 地址 | 推荐模型 |
|--------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | gpt-4o-mini |
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash |

也可以点击预设按钮快速填入常用配置。

> **新克隆仓库后必须自己配一次 Key**：`backend/ai_config.json` 与 `backend/.encryption_key`
> 已加入 `.gitignore`（不入库），服务首次启动时会自动生成，需在界面重新填写。
> API Key 在磁盘上是加密存储的，但请勿把这两个文件提交到任何仓库。

### 4. 开始使用

API 文档: `http://localhost:8000/docs`

> 更多现状信息（依赖清单、仓库卫生、已知隐患与安全说明）见 [docs/STATUS.md](docs/STATUS.md)。

## 使用流程

1. **上传 PDF** - 在「文档管理」页面上传 PDF 文件，进度条会显示**真实的按页解析进度**
2. **生成知识点** - 在「知识体系」页面选择文档，可调整参与分析的文本块数（默认 20），点击「生成知识点」
   - 读取/写入阶段显示真实百分比；单次 AI 调用阶段显示不确定动画（不会编造百分比）
3. **查看可视化** - 切换「思维导图」和「知识图谱」视图；图谱底部有图例说明层级配色与关系线型
4. **生成学习规划** - 在「学习规划」页面生成学习计划
5. **开始测试** - 在「测试练习」页面生成测验并答题
6. **智能问答** - 在「智能问答」页面针对文档内容提问（BM25 检索原文后由 AI 作答，并标注来源页码）

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/documents/upload` | 上传 PDF |
| GET | `/api/documents` | 文档列表 |
| DELETE | `/api/documents/{id}` | 删除文档 |
| POST | `/api/documents/{id}/knowledge/generate` | 生成知识点 |
| GET | `/api/documents/{id}/knowledge/tree` | 知识点树形结构 |
| GET | `/api/documents/{id}/knowledge/graph` | 知识图谱数据 |
| POST | `/api/documents/{id}/study-plan/generate` | 生成学习规划 |
| GET | `/api/documents/{id}/study-plan` | 学习规划列表 |
| POST | `/api/documents/{id}/quiz/generate` | 生成测验 |
| GET | `/api/documents/{id}/quizzes` | 测验列表 |
| POST | `/api/quizzes/{id}/start` | 开始测验 |
| POST | `/api/quiz-attempts/{id}/submit` | 提交答案 |
| POST | `/api/documents/{id}/ask` | 智能问答 |
| GET | `/api/progress/{kind}/{document_id}` | **统一进度查询**（`kind`: `parse`/`knowledge`/`study_plan`/`quiz`） |
| GET | `/api/config` · `POST /api/config` | 读取 / 保存 AI 配置（Key 返回时脱敏） |
| POST | `/api/config/test` | 测试 AI 连接 |

进度载荷的关键字段：`status`、`stage_index`/`total_stages`、`stage_label`、`mode`、`percent`。
当 `mode == "indeterminate"`（单次 AI 调用等不可计数阶段）时 **`percent` 恒为 `null`** —— 界面只显示动画与已用时长，绝不编造百分比。

## 数据处理流程

```
PDF 上传
  ↓
读取页 → 提取文字 → 识别章节 → 文本清洗 → 分块 → 保存
  ↓
AI 提取知识点 → 构建知识树 → 生成关系图谱
  ↓
AI 生成学习规划 / AI 出题 / BM25 检索 + AI 问答
```

> 各环节的进度上报点：解析按**页**计数；知识点/规划/出题按**读取条数**与**写入行数**计数；
> 其中单次 AI 调用阶段为不确定态。

## 开发说明

### 后端开发

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

### 前端开发

前端是纯静态文件，修改后刷新页面即可。

如需单独启动前端服务器：

```bash
cd frontend
python -m http.server 3000
```

## License

MIT
