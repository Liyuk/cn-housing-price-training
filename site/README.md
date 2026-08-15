# 交互式 Demo 站点

本目录是仓库的 GitHub Pages 静态站点，用于可视化项目的数据、方法与预测结果。

## 内容

- `index.html` — 单页看板（中文）
- `styles.css` — 样式与主题（浅色/深色）
- `app.js` — 图表渲染（ECharts 5，经 CDN 加载）
- `data/*.json` — 由 `scripts/build_demo_data.py` 从 `data/processed/` 的 CSV 预生成的数据包
- `.nojekyll` — 让 GitHub Pages 不经过 Jekyll 处理

## 本地预览

```bash
python3 -m http.server 8080 --directory site
# 访问 http://localhost:8080
```

注意：请用 HTTP 服务器预览（而非直接打开文件），否则浏览器的 `fetch` 会被同源策略拦截。

## 重新生成数据

图表数据源是仓库里 git 忽略的 `data/processed/*.csv`。要重新生成 `data/*.json`：

```bash
.venv/bin/python scripts/build_demo_data.py
```

## 部署

推送到 `main` 且 `site/**` 有变化时，`.github/workflows/deploy-demo.yml` 会自动把 `site/` 部署到 GitHub Pages。站点根路径为 `/cn-housing-price-training/`，因此 `app.js` 中所有资源都使用相对路径。
