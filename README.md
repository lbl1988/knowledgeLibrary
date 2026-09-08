# 知识库云版 —— 本地知识库 → 外网可访问网站

## 架构

```
Render（FastAPI 512MB）
  ├── Pinecone（向量，10万免费）
  ├── Cloudflare R2（存储，10GB免费，无限出站）
  ├── Jina AI（嵌入 + 全网搜索，1000万token免费）
  └── Supabase Auth（登录，无限免费用户）
```

全部 0 元，免费版完全够用。

## 快速开始（本地开发）

```bash
cd kb_cloud
pip install -r requirements.txt
cp .env.example .env   # 填好各个 API Key
uvicorn app.main:app --reload --port 8080
```

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
2. 填好 API Key 到 render.yaml 的 envVars 或 Render 控制台
3. 推 GitHub → Render 连仓库 → 自动部署
4. Render 给的 URL → 配置 Supabase Auth 的允许域名
5. 访问 Render URL → 登录 → 搜索

## 注册服务速查

| 服务 | 注册地址 | 免费额度 |
|---|---|---|
| Pinecone | pinecone.io | 10万向量 |
| Cloudflare | dash.cloudflare.com | R2 10GB |
| Jina AI | jina.ai | 1000万token（嵌入+搜索） |
| Supabase | supabase.com | 无限用户 |
| Render | render.com | 512MB |

## 免费额度校验

| 资源 | 用量 | 免费额度 | 够？ |
|---|---|---|---|
| Pinecone 向量 | 46247 | 100000 | ✅ |
| R2 存储 | ~1.4GB | 10GB | ✅ |
| R2 出站 | 无限 | 无限 | ✅ |
| Jina 嵌入 | 46万token | 1000万 | ✅ |
| Jina 搜索 | ~50次/月 | 1000次（约） | ✅ |

## 禁用认证（开发调试）

.env 里设 `SUPABASE_ENABLE_AUTH=false`，首页直接打开不跳登录。

## API 速查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/browse/overview` | 总览 |
| GET | `/api/browse/dirs` | 按目录汇总 |
| GET | `/api/browse/types` | 按类型汇总 |
| GET | `/api/browse/files?folder=&ext=&source=` | 文件列表 |
| GET | `/api/search?q=&limit=` | 语义搜索 |
| GET | `/api/chunk/{doc_id}/{chunk_index}` | chunk 详情 |
| GET | `/api/open/original/{doc_id}` | 原文件预签名 URL |
| GET | `/api/open/extracted/{doc_id}` | 提取文本预签名 URL |
| POST | `/api/crawl` | 全网抓取入库 |
| GET | `/health` | 健康检查 |
