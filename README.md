# 知识库云版 —— 本地知识库 → 外网可访问网站

PLC · 标准化 · 学习资料 + 全网搜索，部署在 Render 上的完整知识库 Web 应用。

在线体验：<https://knowledgelibrary.onrender.com>

## 架构

```
Render（FastAPI 512MB）
  ├── Pinecone（向量，10万免费）
  ├── Cloudflare R2（存储，10GB免费，无限出站）
  ├── Jina AI（嵌入 + 全网搜索，1000万token免费）
  └── Supabase Auth（登录，无限免费用户）
        └── JWT 验证：从 JWKS 端点动态获取公钥
            自动兼容 ECC (ES256) 和 HS256 两种签名算法
```

全部 0 元，免费版完全够用。

## 快速开始（本地开发）

```bash
cd knowledgeLibrary
pip install -r requirements.txt
cp .env.example .env   # 填好各个 API Key
uvicorn app.main:app --reload --port 8080
```

## Supabase Auth 配置

Supabase 已于 2025 年将 JWT 签名从 HS256 迁移到 ECC P-256（ES256），**旧的 Legacy JWT Secret 已废弃**。

后端已适配：自动从 `SUPABASE_URL/auth/v1/.well-known/jwks.json` 动态获取公钥，无需硬编码密钥。

**环境变量（Render / .env）：**

| 变量                     | 值                                   | 说明                                          |
| ---------------------- | ----------------------------------- | ------------------------------------------- |
| `SUPABASE_URL`         | `https://<project-ref>.supabase.co` | Supabase 项目 URL                             |
| `SUPABASE_ANON_KEY`    | `sb_publishable_...`（新格式）           | **新的 Publishable Key**，不是旧的 JWT 格式 anon key |
| `SUPABASE_ENABLE_AUTH` | `true`                              | 设为 `false` 可跳过认证（仅本地调试）                     |

> ⚠️ **关键**：`SUPABASE_ANON_KEY` 必须用 Supabase Dashboard → API Keys 页面的 **Publishable Key**（`sb_publishable_` 开头），旧的 Legacy anon key（`eyJhbGci...` 开头）Supabase Auth API 已拒绝。

### Supabase Dashboard 设置

1. **关闭邮箱确认**（注册后自动登录）：Authentication → Providers → Email → Enable email provider → **关闭 "Confirm email"**
2. **添加允许域名**：Authentication → URL Configuration → Site URL 和 Additional Redirect URLs 加入 Render 域名（如 `https://knowledgelibrary.onrender.com`）

## 迁移本地数据

```bash
# 填好 .env 里的 LOCAL_KB_DIR 指向本地 kb_src/
cd data
python migrate.py
```

脚本会自动：

1. 读本地 SQLite kb.db（173 文档 + 46247 chunk）
2. 上传原文件到 R2 kb-originals/
3. 上传提取文本到 R2 kb-extracted/
4. 用 Jina API 重新嵌入所有 chunk
5. upsert 到 Pinecone

## 部署 Render

1. 注册 Pinecone / Cloudflare / Jina AI / Supabase / Render（各 5 分钟）
2. 填好 API Key 到 `render.yaml` 的 `envVars` 或 Render 控制台
3. 推 GitHub → Render 连仓库 → 自动部署
4. Render 给的 URL → 配置 Supabase Auth 的允许域名
5. 访问 Render URL → 注册 → 登录 → 搜索

## 注册服务速查

| 服务         | 注册地址                | 免费额度              |
| ---------- | ------------------- | ----------------- |
| Pinecone   | pinecone.io         | 10万向量             |
| Cloudflare | dash.cloudflare.com | R2 10GB           |
| Jina AI    | jina.ai             | 1000万token（嵌入+搜索） |
| Supabase   | supabase.com        | 无限用户              |
| Render     | render.com          | 512MB             |

## 免费额度校验

| 资源          | 用量       | 免费额度     | 够？ |
| ----------- | -------- | -------- | -- |
| Pinecone 向量 | 46247    | 100000   | ✅  |
| R2 存储       | \~1.4GB  | 10GB     | ✅  |
| R2 出站       | 无限       | 无限       | ✅  |
| Jina 嵌入     | 46万token | 1000万    | ✅  |
| Jina 搜索     | \~50次/月  | 1000次（约） | ✅  |

## 禁用认证（开发调试）

`.env` 或 Render Environment Variables 设 `SUPABASE_ENABLE_AUTH=false`，首页直接打开不跳登录。

## 项目结构

```
knowledgeLibrary/
├── app/
│   ├── auth.py           # Supabase JWT 鉴权（JWKS 动态公钥，支持 ES256/HS256）
│   ├── config.py         # 环境变量加载
│   ├── main.py           # FastAPI 入口
│   ├── routes/           # API 路由
│   │   ├── browse.py     # 浏览（目录/类型/文件列表）
│   │   ├── search.py     # 语义搜索 + 全网搜索
│   │   ├── open_doc.py   # 打开原文件/提取文本（R2 预签名 URL）
│   │   └── crawl.py      # 全网抓取入库
│   ├── services/         # 业务服务
│   │   ├── vectorstore.py  # Pinecone 封装
│   │   ├── storage.py      # Cloudflare R2 封装
│   │   ├── embedder.py     # Jina Embeddings
│   │   ├── parser.py       # 文档解析
│   │   ├── chunker.py      # 文本分块
│   │   └── crawler.py      # 网页抓取
│   └── templates/
│       └── index.html    # 前端单页（登录 + 浏览 + 搜索）
├── data/
│   └── migrate.py        # 本地数据迁移脚本
├── requirements.txt
├── requirements-migrate.txt
├── .env.example
├── render.yaml
└── README.md
```

## API 速查

所有 API 需在 `Authorization: Bearer <token>` 头携带 Supabase access\_token（`SUPABASE_ENABLE_AUTH=false` 时跳过）。

| 方法   | 路径                                       | 说明                       |
| ---- | ---------------------------------------- | ------------------------ |
| GET  | `/api/browse/overview`                   | 总览（文档数、chunk 数、按目录/类型分布） |
| GET  | `/api/browse/dirs`                       | 按目录汇总                    |
| GET  | `/api/browse/types`                      | 按文件类型汇总                  |
| GET  | `/api/browse/files?folder=&ext=&source=` | 文件列表                     |
| GET  | `/api/search?q=&limit=`                  | 语义搜索（Pinecone 向量相似度）     |
| GET  | `/api/crawl?q=&limit=`                   | 全网搜索（Jina SearchAPI）     |
| GET  | `/api/chunk/{doc_id}/{chunk_index}`      | chunk 详情                 |
| GET  | `/api/open/original/{doc_id}`            | 原文件预签名 URL               |
| GET  | `/api/open/extracted/{doc_id}`           | 提取文本预签名 URL              |
| POST | `/api/crawl`                             | 全网抓取入库                   |
| GET  | `/health`                                | 健康检查（无需认证）               |

## 技术栈

- **后端**：FastAPI + python-jose + cryptography

- **前端**：原生 HTML/JS + Supabase JS Client（CDN）

- **向量库**：Pinecone

- **对象存储**：Cloudflare R2

- **嵌入/搜索**：Jina AI

- **认证**：Supabase Auth（JWT，JWKS 动态验证）

- **部署**：Render（自动从 GitHub 构建）

