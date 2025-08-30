import os
import json
import sys
import io
import random
import time
import base64
import re
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ------------------------
# 配置
# ------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME")
REPO_NAME = os.environ.get("GITHUB_REPO")  # 当前仓库名
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID")
VERCEL_PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID")

if not all([GITHUB_TOKEN, GITHUB_USERNAME, REPO_NAME]):
    print("❌ 必须设置 GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_REPO 环境变量")
    sys.exit(1)

GITHUB_API = "https://api.github.com"

# ------------------------
# Google Drive 配置
# ------------------------
service_account_info = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
if not service_account_info:
    print("❌ 未找到 GDRIVE_SERVICE_ACCOUNT 环境变量")
    sys.exit(1)
try:
    service_account_info = json.loads(service_account_info)
except json.JSONDecodeError:
    print("❌ 解析 GDRIVE_SERVICE_ACCOUNT 失败")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

folder_ids_str = os.environ.get("GDRIVE_FOLDER_ID")
if not folder_ids_str:
    print("❌ 未找到 GDRIVE_FOLDER_ID 环境变量")
    sys.exit(1)
FOLDER_IDS = [fid.strip() for fid in folder_ids_str.split(",") if fid.strip()]

# ------------------------
# 读取关键词
# ------------------------
keywords = []
keywords_file = "keywords.txt"
if os.path.exists(keywords_file):
    with open(keywords_file, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

# ------------------------
# 已处理文件缓存
# ------------------------
processed_file_path = "processed_files.json"
try:
    if os.path.exists(processed_file_path):
        with open(processed_file_path, "r") as f:
            processed_data = json.load(f)
    else:
        processed_data = {"fileIds": []}
except:
    processed_data = {"fileIds": []}

# ------------------------
# Google Drive 文件列表
# ------------------------
def list_files(folder_id):
    all_files = []
    page_token = None
    query = f"'{folder_id}' in parents and (mimeType='text/html' or mimeType='text/plain' or mimeType='application/vnd.google-apps.document')"
    while True:
        results = service.files().list(q=query, pageSize=1000,
                                       fields="nextPageToken, files(id, name, mimeType)", pageToken=page_token).execute()
        items = results.get('files', [])
        all_files.extend(items)
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return all_files

# ------------------------
# 下载文件函数
# ------------------------
def download_html_file(file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue().decode('utf-8')

def download_txt_file(file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text = fh.getvalue().decode('utf-8')
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body><pre>{text}</pre></body></html>"
    return html

def export_google_doc(file_id):
    request = service.files().export_media(fileId=file_id, mimeType='text/html')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue().decode('utf-8')

# ------------------------
# GitHub API 上传文件
# ------------------------
def github_upload_file(path, content):
    url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # 检查文件是否存在
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json()["sha"]
        data = {
            "message": f"Auto deploy {path}",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "sha": sha,
            "branch": "main"
        }
    else:
        data = {
            "message": f"Auto deploy {path}",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main"
        }

    r = requests.put(url, headers=headers, json=data)
    if r.status_code in [200, 201]:
        print(f"✅ {path} 上传成功")
    else:
        print(f"❌ 上传 {path} 失败: {r.text}")

# ------------------------
# Netlify / Vercel 部署
# ------------------------
def deploy_netlify():
    if not NETLIFY_TOKEN or not NETLIFY_SITE_ID:
        return
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    r = requests.post(f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys", headers=headers)
    print(f"Netlify 部署状态: {r.status_code}")

def deploy_vercel():
    if not VERCEL_TOKEN or not VERCEL_PROJECT_ID:
        return
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
    r = requests.post("https://api.vercel.com/v13/deployments", headers=headers, json={"project": VERCEL_PROJECT_ID})
    print(f"Vercel 部署状态: {r.status_code}")

# ------------------------
# 主程序
# ------------------------
all_files = []
for fid in FOLDER_IDS:
    all_files.extend(list_files(fid))

new_files = [f for f in all_files if f['id'] not in processed_data.get("fileIds", [])]

# 处理文件
for f in new_files:
    base_name = f['name'].replace(" ", "-")
    if f['mimeType'] == 'text/html':
        html = download_html_file(f['id'])
    elif f['mimeType'] == 'text/plain':
        html = download_txt_file(f['id'])
    else:
        html = export_google_doc(f['id'])
    processed_data["fileIds"].append(f['id'])

    # 上传 HTML 文件
    github_upload_file(base_name, html)

# 保存 processed 文件
with open(processed_file_path, "w") as f:
    json.dump(processed_data, f, indent=2)

# ------------------------
# 生成 index.html（sitemap）
# ------------------------
all_html_files = [f['name'].replace(" ", "-") for f in all_files]
index_html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Sitemap</title></head><body><h1>Sitemap</h1><ul>\n"
for file in all_html_files:
    index_html += f'<li><a href="{file}">{file}</a></li>\n'
index_html += "</ul></body></html>"

github_upload_file("index.html", index_html)

# ------------------------
# 底部随机内部链接
# ------------------------
for f in all_html_files:
    try:
        # 获取内容
        url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{f}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            continue
        content_json = r.json()
        html_content = base64.b64decode(content_json['content']).decode('utf-8')

        # 移除旧 footer
        html_content = re.sub(r"<footer>.*?</footer>", "", html_content, flags=re.DOTALL | re.IGNORECASE)

        # 添加随机内部链接
        other_files = [x for x in all_html_files if x != f]
        num_links = min(len(other_files), random.randint(4,6))
        links_html = ""
        if num_links > 0:
            random_links = random.sample(other_files, num_links)
            links_html = "<footer><ul>\n" + "\n".join([f'<li><a href="{x}">{x}</a></li>' for x in random_links]) + "\n</ul></footer>"

        # 确保 </body></html> 存在
        html_content = re.sub(r"</body>\s*</html>.*$", "", html_content, flags=re.IGNORECASE)
        html_content = html_content.strip() + "\n" + links_html + "</body></html>"

        # 上传更新后的 HTML
        github_upload_file(f, html_content)
    except Exception as e:
        print(f"❌ 无法为 {f} 添加内部链接: {e}")

# ------------------------
# 触发部署
# ------------------------
deploy_netlify()
deploy_vercel()

print("✅ 部署完成！")
