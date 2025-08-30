name: Auto Update HTML from Google Drive

# 手动触发 + 定时触发（每6小时一次）
on:
  workflow_dispatch:
  schedule:
    - cron: "0 */6 * * *"

jobs:
  update-html:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # ⚡ 给 GITHUB_TOKEN 上传文件权限

    steps:
      # 1️⃣ 检出仓库
      - name: Checkout repository
        uses: actions/checkout@v3

      # 2️⃣ 安装 Python
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      # 3️⃣ 安装依赖
      - name: Install dependencies
        run: |
          pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib requests

      # 4️⃣ 运行 auto_deploy.py
      - name: Run auto_deploy.py
        env:
          # Google Drive 配置
          GDRIVE_SERVICE_ACCOUNT: ${{ secrets.GDRIVE_SERVICE_ACCOUNT }}
          GDRIVE_FOLDER_ID: ${{ secrets.GDRIVE_FOLDER_ID }}

          # GitHub Actions 自带 token，用于上传到当前仓库
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}

          # Netlify 部署
          NETLIFY_TOKEN: ${{ secrets.NETLIFY_TOKEN }}
          NETLIFY_SITE_ID: ${{ secrets.NETLIFY_SITE_ID }}

          # Vercel 部署
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
        run: python auto_deploy.py
