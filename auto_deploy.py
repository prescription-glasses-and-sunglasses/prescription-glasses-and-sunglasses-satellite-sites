# auto_deploy.py - 自动部署卫星站点到 Netlify 和 Vercel
import os
import sys
import csv
import time
import json
import random
import shutil
import logging
import requests
from pathlib import Path
from typing import List, Optional
from setup_github import GitHubSetup

# -----------------------------
# 日志配置
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -----------------------------
# 配置
# -----------------------------
CONFIG_FILE = Path("config.csv")
ARTICLES_DIR = Path("articles")  # 存放 HTML 文章
MAX_DEPLOY = 10                  # 每次部署的文章数
REQUEST_TIMEOUT = 30             # API超时时间（秒）


class DeployManager:
    def __init__(self):
        self.config = self.load_config()
        self.github = GitHubSetup(self.config["github_token"], self.config["github_username"])
        self.netlify_sites: List[str] = []
        self.vercel_sites: List[str] = []

    def load_config(self) -> dict:
        """加载配置文件"""
        if not CONFIG_FILE.exists():
            logger.error(f"配置文件 {CONFIG_FILE} 不存在")
            sys.exit(1)

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return next(reader)

    def get_random_articles(self, count: int) -> List[Path]:
        """随机选取文章"""
        if not ARTICLES_DIR.exists():
            logger.error(f"文章目录 {ARTICLES_DIR} 不存在")
            return []

        all_articles = list(ARTICLES_DIR.glob("*.html"))
        if not all_articles:
            logger.error(f"{ARTICLES_DIR} 没有找到 HTML 文章")
            return []

        return random.sample(all_articles, min(count, len(all_articles)))

    def prepare_repo_content(self, repo_dir: Path, articles: List[Path]):
        """准备临时仓库内容"""
        repo_dir.mkdir(parents=True, exist_ok=True)

        for article in articles:
            shutil.copy2(article, repo_dir)

        # 生成 index.html
        index_content = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>文章列表</title>
</head>
<body>
  <h1>文章列表</h1>
  <ul>
"""
        for article in articles:
            index_content += f'    <li><a href="{article.name}">{article.stem}</a></li>\n'

        index_content += """  </ul>
</body>
</html>"""

        with open(repo_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(index_content)

    def push_to_github(self, repo_name: str, repo_dir: Path) -> Optional[str]:
        """上传内容到 GitHub"""
        repo = self.github.create_repo(repo_name, is_private=True)
        if not repo:
            return None

        for file in repo_dir.glob("*"):
            self.github.upload_file(repo_name, str(file), github_path=file.name, commit_message="Add content")

        return f"https://github.com/{self.config['github_username']}/{repo_name}"

    def deploy_to_netlify(self, repo_url: str) -> Optional[str]:
        """部署到 Netlify"""
        try:
            headers = {"Authorization": f"Bearer {self.config['netlify_token']}"}
            data = {
                "name": f"site-{int(time.time())}-{random.randint(1000,9999)}",
                "repo": {
                    "provider": "github",
                    "repo": repo_url.replace("https://github.com/", ""),
                    "branch": "main"
                }
            }
            response = requests.post("https://api.netlify.com/api/v1/sites", headers=headers, json=data, timeout=REQUEST_TIMEOUT)

            if response.status_code in [200, 201]:
                site_url = response.json().get("url")
                logger.info(f"成功部署到 Netlify: {site_url}")
                return site_url
            else:
                logger.error(f"Netlify 部署失败: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Netlify 出错: {e}")
            return None

    def deploy_to_vercel(self, repo_url: str) -> Optional[str]:
        """部署到 Vercel"""
        try:
            headers = {"Authorization": f"Bearer {self.config['vercel_token']}"}
            data = {
                "name": f"site-{int(time.time())}-{random.randint(1000,9999)}",
                "gitRepository": {"type": "github", "repo": repo_url.replace("https://github.com/", ""), "branch": "main"}
            }
            response = requests.post("https://api.vercel.com/v9/projects", headers=headers, json=data, timeout=REQUEST_TIMEOUT)

            if response.status_code in [200, 201]:
                project = response.json()
                site_url = f"https://{project['name']}.vercel.app"
                logger.info(f"成功部署到 Vercel: {site_url}")
                return site_url
            else:
                logger.error(f"Vercel 部署失败: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Vercel 出错: {e}")
            return None

    def generate_sitemap(self, output_file: Path):
        """生成 sitemap.html"""
        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>卫星站点地图</title></head>
<body>
  <h1>卫星站点地图</h1>
  <p>生成时间: %s</p>
  <h2>Netlify</h2><ul>""" % time.strftime("%Y-%m-%d %H:%M:%S")

        for url in self.netlify_sites:
            html += f"<li><a href='{url}' target='_blank'>{url}</a></li>"

        html += "</ul><h2>Vercel</h2><ul>"

        for url in self.vercel_sites:
            html += f"<li><a href='{url}' target='_blank'>{url}</a></li>"

        html += "</ul></body></html>"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"站点地图已生成: {output_file}")

    def run(self):
        """执行部署流程"""
        articles = self.get_random_articles(MAX_DEPLOY)
        if not articles:
            logger.error("没有找到文章")
            return False

        repo_name = f"satellite-{int(time.time())}"
        temp_dir = Path(f"temp_repo")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        self.prepare_repo_content(temp_dir, articles)
        github_url = self.push_to_github(repo_name, temp_dir)
        shutil.rmtree(temp_dir)

        if not github_url:
            logger.error("推送 GitHub 失败")
            return False

        netlify_url = self.deploy_to_netlify(github_url)
        if netlify_url:
            self.netlify_sites.append(netlify_url)

        vercel_url = self.deploy_to_vercel(github_url)
        if vercel_url:
            self.vercel_sites.append(vercel_url)

        self.generate_sitemap(Path("sitemap.html"))
        logger.info("部署完成")
        return True


if __name__ == "__main__":
    deployer = DeployManager()
    success = deployer.run()
    sys.exit(0 if success else 1)
