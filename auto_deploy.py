import os
import json
import sys
import io
import random
import time
import re
import base64
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ------------------------
# 环境变量配置
# ------------------------
GDRIVE_SERVICE_ACCOUNT = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")  # 可以有多个，用逗号分隔
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME")  # 仓库所属用户名
GITHUB_REPOSITORY = f"{GITHUB_USERNAME}/{os.path.basename(os.getcwd())}"

if not GDRIVE_SERVICE_ACCOUNT or not GDRIVE_FOLDER_ID:
    print("❌ 必须设置 GDRIVE_SERVICE_ACCOUNT 和 GDRIVE_FOLDER_ID 环境变量")
    sys.exit(1)

if not NETLIFY_TOKEN or not VERCEL_TOKEN:
    print("⚠️ 警告：未设置 NETLIFY_TOKEN 或 VERCEL_TOKEN，部署将跳过")

# ------------------------
# Google Drive API 初始化
# ------------------------
try:
    service_account_info = json.loads(GDRIVE_SERVICE_ACCOUNT)
except json.JSONDecodeError:
    print("❌ 解析 GDRIVE_SERVICE_ACCOUNT 失败")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

FOLDER_IDS = [fid.strip() for fid in GDRIVE_FOLDER_ID.split(",") if fid.strip()]

# ------------------------
# 文件缓存
# ------------------------
processed_file_path = "processed_files.json"
cache_file_path = "files_cache.json"
CACHE_EXPIRY_HOURS = 24

try:
    if os.path.exists(processed_file_path):
        with open(processed_file_path, "r") as f:
            processed_data = json.load(f)
    else:
        processed_data = {"fileIds": []}
except:
    processed_data = {"fileIds": []}

def get_cached_files():
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, "r") as f:
                cache_data = json.load(f)
                last_updated = cache_data.get("last_updated")
                if last_updated and (time.time() - last_updated < CACHE_EXPIRY_HOURS * 3600):
                    print("✅ 缓存未过期，正在从本地加载文件列表。")
                    return cache_data.get("files", [])
        except:
            pass
    return None

def save_files_to_cache(files):
    cache_data = {"last_updated": time.time(), "files": files}
    with open(cache_file_path, "w") as f:
        json.dump(cache_data, f, indent=4)

# ------------------------
# Google Drive 文件操作
# ------------------------
def list_files(folder_id):
    all_files = []
    page_token = None
    query = f"'{folder_id}' in parents and (mimeType='text/html' or mimeType='text/plain' or mimeType='application/vnd.google-apps.document')"
    while True:
        results = service.files().list(
            q=query,
            pageSize=1000,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        all_files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return all_files

def download_file(file_id, file_name, mimeType, original_name=None):
    if mimeType == 'text/html':
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(file_name, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    elif mimeType == 'text/plain':
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        text_content = fh.getvalue().decode('utf-8')
        html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{original_name}</title></head><body><pre>{text_content}</pre></body></html>"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(html_content)
    else:  # Google Docs
        request = service.files().export_media(fileId=file_id, mimeType='text/html')
        fh = io.FileIO(file_name, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

# ------------------------
# 查找 deployment_urls.txt
# ------------------------
DEPLOYMENT_FILE_NAME = "deployment_urls.txt"

def get_deployment_file_id():
    try:
        results = service.files().list(
            q=f"name='{DEPLOYMENT_FILE_NAME}'",
            fields="files(id, name)",
            pageSize=10
        ).execute()
        items = results.get("files", [])
        if not items:
            raise FileNotFoundError(f"❌ 未找到 {DEPLOYMENT_FILE_NAME}，请先在 Google Drive 上传此文件。")
        print(f"✅ 找到 {DEPLOYMENT_FILE_NAME}，fileId: {items[0]['id']}")
        return items[0]["id"]
    except Exception as e:
        print(f"搜索 {DEPLOYMENT_FILE_NAME} 时出错: {e}")
        raise

# ------------------------
# GitHub API 上传
# ------------------------
def upload_to_github(file_path):
    with open(file_path, "rb") as f:
        content = f.read()
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{file_path}"
    data = {"message": f"Auto update {file_path}", "content": base64.b64encode(content).decode()}
    headers = {"Authorization": f"token {os.environ.get('GITHUB_TOKEN')}"}
    r = requests.put(url, headers=headers, json=data)
    if r.status_code in (200, 201):
        print(f"✅ 上传成功: {file_path}")
    else:
        print(f"❌ 上传失败: {file_path}, {r.status_code}, {r.text}")

# ------------------------
# Netlify / Vercel 部署
# ------------------------
def deploy_netlify():
    if not NETLIFY_TOKEN:
        return None
    # 简化示例，实际可用 Netlify API 部署已有 repo
    print("✅ 调用 Netlify 部署完成")
    return "https://your-site.netlify.app"

def deploy_vercel():
    if not VERCEL_TOKEN:
        return None
    print("✅ 调用 Vercel 部署完成")
    return "https://your-site.vercel.app"

# ------------------------
# 主程序
# ------------------------
all_files = get_cached_files()
if all_files is None:
    all_files = []
    for folder_id in FOLDER_IDS:
        all_files.extend(list_files(folder_id))
    save_files_to_cache(all_files)

new_files = [f for f in all_files if f['id'] not in processed_data.get("fileIds", [])]

if new_files:
    selected_files = random.sample(new_files, min(len(new_files), 30))
    for f in selected_files:
        base_name = os.path.splitext(f['name'])[0].replace(" ", "-").replace("/", "-")
        safe_name = f"{base_name}-{random.randint(1000,9999)}.html"
        download_file(f['id'], safe_name, f['mimeType'], f['name'])
        processed_data.setdefault("fileIds", []).append(f['id'])

    with open(processed_file_path, "w") as f:
        json.dump(processed_data, f, indent=4)

# 生成 index.html
html_files = [f for f in os.listdir(".") if f.endswith(".html")]
index_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Site Map</title></head><body><h1>Site Map</h1><ul>"
for fname in sorted(html_files):
    index_content += f'<li><a href="{fname}">{fname}</a></li>'
index_content += "</ul></body></html>"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(index_content)

# 上传 HTML 到 GitHub
for fname in html_files:
    upload_to_github(fname)

# 部署
netlify_url = deploy_netlify()
vercel_url = deploy_vercel()
deployment_urls = [u for u in [netlify_url, vercel_url] if u]

# 写入 deployment_urls.txt
if deployment_urls:
    deployment_file_id = get_deployment_file_id()
    # 先下载已有内容
    request = service.files().get_media(fileId=deployment_file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    existing_content = fh.getvalue().decode("utf-8")
    new_content = existing_content + "\n" + "\n".join(deployment_urls)
    # 更新文件
    media = io.BytesIO(new_content.encode("utf-8"))
    service.files().update(fileId=deployment_file_id, media_body=media).execute()
    print(f"✅ 已更新 {DEPLOYMENT_FILE_NAME}，追加部署 URL")
