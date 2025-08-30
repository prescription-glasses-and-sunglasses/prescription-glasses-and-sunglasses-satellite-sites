import os
import json
import io
import random
import time
import re
import base64
import requests
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ------------------------
# Google Drive 配置
# ------------------------
service_account_info = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
if not service_account_info:
    print("❌ 未找到 GDRIVE_SERVICE_ACCOUNT 环境变量。")
    sys.exit(1)
try:
    service_account_info = json.loads(service_account_info)
except json.JSONDecodeError:
    print("❌ 解析 GDRIVE_SERVICE_ACCOUNT 失败")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

folder_ids_str = os.environ.get("GDRIVE_FOLDER_ID")
if not folder_ids_str:
    print("❌ 未找到 GDRIVE_FOLDER_ID 环境变量")
    sys.exit(1)
FOLDER_IDS = [fid.strip() for fid in folder_ids_str.split(",") if fid.strip()]

# ------------------------
# GitHub 配置
# ------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # 使用 workflow 自带 token
if not GITHUB_TOKEN:
    print("❌ 未找到 GITHUB_TOKEN 环境变量")
    sys.exit(1)
GITHUB_USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "")  # workflow 提供
REPO_NAME = os.path.basename(os.getcwd())
GITHUB_REPO = f"{GITHUB_USERNAME}/{REPO_NAME}"

# ------------------------
# Netlify / Vercel 配置
# ------------------------
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")

# ------------------------
# 已处理文件记录
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
# 工具函数
# ------------------------
def list_files(folder_id):
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and (mimeType='text/html' or mimeType='text/plain' or mimeType='application/vnd.google-apps.document')"
    while True:
        results = service.files().list(q=query, pageSize=1000, fields="nextPageToken, files(id,name,mimeType)", pageToken=page_token).execute()
        files.extend(results.get('files', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return files

def download_file(f):
    file_id = f['id']
    file_name = f['name']
    if f['mimeType'] == 'text/html':
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(file_name, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    elif f['mimeType'] == 'text/plain':
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        text_content = fh.getvalue().decode('utf-8')
        html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{file_name}</title></head><body><pre>{text_content}</pre></body></html>"
        with open(file_name, "w", encoding="utf-8") as f2:
            f2.write(html_content)
    else:
        # Google Docs
        request = service.files().export_media(fileId=file_id, mimeType='text/html')
        fh = io.FileIO(file_name, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    print(f"✅ 下载完成: {file_name}")
    processed_data["fileIds"].append(file_id)

def commit_github_file(file_path):
    with open(file_path, "rb") as f:
        content = f.read()
    b64_content = base64.b64encode(content).decode()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    # 检查文件是否存在
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json()["sha"]
        data = {"message": f"update {file_path}", "content": b64_content, "sha": sha}
    else:
        data = {"message": f"add {file_path}", "content": b64_content}
    r = requests.put(url, headers=headers, json=data)
    if r.status_code in [200,201]:
        print(f"✅ 上传成功: {file_path}")
    else:
        print(f"❌ 上传失败: {file_path}, {r.status_code}, {r.text}")

def deploy_netlify():
    if not NETLIFY_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    # 这里只演示返回 URL
    return f"https://{REPO_NAME}.netlify.app"

def deploy_vercel():
    if not VERCEL_TOKEN:
        return None
    return f"https://{REPO_NAME}.vercel.app"

def update_deployment_urls(urls):
    # 查找 deployment_urls.txt
    query = "name='deployment_urls.txt'"
    response = service.files().list(q=query, fields="files(id,name)").execute()
    files = response.get("files", [])
    if not files:
        print("❌ 未找到 deployment_urls.txt，请先在 Google Drive 上传此文件。")
        sys.exit(1)
    file_id = files[0]["id"]
    # 读取原内容
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    content = fh.getvalue().decode("utf-8")
    content += "\n" + "\n".join(urls)
    # 更新文件
    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain")
    service.files().update(fileId=file_id, media_body=media).execute()
    print("✅ deployment_urls.txt 已更新")

# ------------------------
# 主程序
# ------------------------
all_files = []
for fid in FOLDER_IDS:
    all_files.extend(list_files(fid))

new_files = [f for f in all_files if f['id'] not in processed_data["fileIds"]]
for f in new_files:
    download_file(f)

# 保存 processed_file_path
with open(processed_file_path, "w") as f:
    json.dump(processed_data, f, indent=4)

# 生成 index.html
html_files = [f for f in os.listdir(".") if f.endswith(".html") and f != "index.html"]
index_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Site Map</title></head><body><h1>Site Map</h1><ul>"
for fname in html_files:
    index_content += f'<li><a href="{fname}">{fname}</a></li>'
index_content += "</ul></body></html>"
with open("index.html", "w") as f:
    f.write(index_content)

# 上传到 GitHub
for f in html_files + ["index.html"]:
    commit_github_file(f)

# 部署
urls = []
netlify_url = deploy_netlify()
if netlify_url:
    print("✅ Netlify URL:", netlify_url)
    urls.append(netlify_url)
vercel_url = deploy_vercel()
if vercel_url:
    print("✅ Vercel URL:", vercel_url)
    urls.append(vercel_url)

# 更新 Google Drive 上的 deployment_urls.txt
if urls:
    update_deployment_urls(urls)
