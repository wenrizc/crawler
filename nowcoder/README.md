# Crawler 项目说明

本项目聚焦于各类爬虫实践，目前已包含牛客网面经抓取与整理流程，可扩展到更多站点和内容类型。

## 功能概览
- 通过 Playwright 进行页面交互与接口监听，收集面经 UUID
- 使用 Requests 抓取详情页并解析标题与内容
- 生成结构化 JSON 数据
- 可选调用智谱 AI 对内容进行提炼与整理，输出 Markdown

## 目录结构
```
nowcoder/
  scraper.py                 # 抓取面经列表与详情
  process_interviews.py      # 处理 JSON，生成 Markdown
  nowcoder_scraped_data.json # 抓取输出（示例/结果）
  interview_analysis/        # Markdown 产物目录
  requirements.txt           # 依赖列表
```

## 环境依赖
Python 3.10+（推荐）

安装依赖：
```
pip install -r requirements.txt
```

脚本实际使用到的库还包括 `beautifulsoup4`、`playwright`、`openai`。
如运行报缺包，请补充安装：
```
pip install beautifulsoup4 playwright openai
playwright install
```

## 使用方式
1) 抓取数据（会弹出浏览器，需人工处理登录弹窗）
```
python scraper.py
```
产物：`nowcoder_scraped_data.json`

2) 生成 Markdown（可选：调用智谱 AI）
```
python process_interviews.py
```
产物：`interview_analysis/*.md`

## 配置说明
`process_interviews.py` 中需要可用的 API Key 才能调用智谱 AI。
建议改为使用环境变量读取并避免硬编码密钥。

## 开发规范
- **合法合规**：遵守目标站点的 robots 与服务条款，避免对网站造成压力或影响业务。
- **抓取节制**：设置合理的访问频率与超时，必要时加入退避策略与重试。
- **可复用结构**：新增站点时，保持“列表抓取 → 详情抓取 → 结果处理”的流程拆分。
- **数据可追溯**：输出 JSON 中保留 `url` 与 `uuid` 等关键字段，便于溯源。
- **配置隔离**：Cookie、Token、API Key 统一从环境变量读取，不提交到仓库。
- **日志与排障**：关键阶段输出清晰日志，出错时包含 URL、状态码或异常信息。
- **文件命名**：输出文件使用可读标题 + 序号，避免重名与非法字符。
- **代码风格**：保持函数职责单一；复杂逻辑优先拆分为独立函数或模块。
- **变更验证**：修改抓取逻辑后，至少验证一轮完整流程（抓取 + 处理 + 输出）。

