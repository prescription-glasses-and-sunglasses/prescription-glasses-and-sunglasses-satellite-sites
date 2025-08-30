import os
import sys
import json
import io
import time
import random
import base64
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ------------------------
# Google Drive 配置
# ------------------------
service_account_info = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
if not service_account_info:
    print("❌ 未找到 GDRIVE_SERVICE_ACCOUNT 环境变量")
    sys.exit(1)

service_account_info = json.loads(service_account_info)
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

GDRIVE_FOLDER_IDS = os.environ.get("GDRIVE_FOLDER_ID", "").split(",")
if not GDRIVE_FOLDER_IDS:
    print("❌ 未找到 GDRIVE_FOLDER_ID 环境变量")
    sys.exit(1)

# ------------------------
# GitHub 配置
# ------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("❌ 未找到 GITHUB_TOKEN 环境变量")
    sys.exit(1)

repo_name = os.path.basename(os.getcwd())
GITHUB_USERNAME = os.environ.get("GITHUB_ACTOR")  # Actions 自动提供
GITHUB_REPOSITORY = f"{GITHUB_USERNAME}/{repo_name}"

GITHUB_API = "https://api.github.com"

# ------------------------
# Netlify / Vercel 配置
# ------------------------
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")

VERCEL_PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")

# ------------------------
# 部署 URL 累积文件
# ------------------------
DEPLOYMENT_FILE_NAME = "deployment_urls.txt"

def download_google_file(file_id):
    """下载 Google Drive 文件内容"""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue().decode("utf-8")

def upload_google_file(file_id, content):
    """上传内容到 Google Drive 文件"""
    media = MediaFileUpload("tmp.txt", mimetype="text/plain", resumable=True)
    with open("tmp.txt", "w", encoding="utf-8") as f:
        f.write(content)
    media = MediaFileUpload("tmp.txt", mimetype="text/plain")
    service.files().update(fileId=file_id, media_body=media).execute()
    os.remove("tmp.txt")
    print(f"✅ 已更新 Google Drive 文件 {DEPLOYMENT_FILE_NAME}")

def find_deployment_file():
    """查找 Google Drive 上的 deployment_urls.txt"""
    for folder_id in GDRIVE_FOLDER_IDS:
        query = f"'{folder_id}' in parents and name='{DEPLOYMENT_FILE_NAME}' and trashed=false"
        results = service.files().list(q=query, fields="files(id,name)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
    return None

# ------------------------
# GitHub 上传文件函数
# ------------------------
def github_upload_file(filename):
    with open(filename, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    url = f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/contents/{filename}"
    data = {
        "message": f"Auto update {filename}",
        "content": content_b64
    }
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.put(url, headers=headers, json=data)
    if r.status_code in [200, 201]:
        print(f"✅ 上传成功: {filename}")
    else:
        print(f"❌ 上传失败: {filename}, {r.status_code}, {r.text}")

# ------------------------
# Netlify / Vercel 部署函数
# ------------------------
def deploy_netlify():
    if not NETLIFY_SITE_ID or not NETLIFY_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    r = requests.post(f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys", headers=headers)
    if r.status_code == 200:
        url = r.json().get("deploy_url") or r.json().get("ssl_url")
        print(f"✅ Netlify 部署完成: {url}")
        return url
    else:
        print(f"❌ Netlify 部署失败: {r.status_code}, {r.text}")
        return None

def deploy_vercel():
    if not VERCEL_PROJECT_ID or not VERCEL_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
    r = requests.post(f"https://api.vercel.com/v13/deployments", headers=headers,
                      json={"name": repo_name, "project": VERCEL_PROJECT_ID})
    if r.status_code in [200, 201]:
        url = r.json().get("url")
        print(f"✅ Vercel 部署完成: {url}")
        return url
    else:
        print(f"❌ Vercel 部署失败: {r.status_code}, {r.text}")
        return None

# ------------------------
# 示例：上传 HTML 文件并部署
# ------------------------
html_files = [f for f in os.listdir(".") if f.endswith(".html")]
for f in html_files:
    github_upload_file(f)

netlify_url = deploy_netlify()
vercel_url = deploy_vercel()

# ------------------------
# 更新 Google Drive deployment_urls.txt
# ------------------------
file_id = find_deployment_file()
if not file_id:
    print(f"❌ 没有找到 {DEPLOYMENT_FILE_NAME}，请先上传到 Google Drive")
else:
    try:
        existing_content = download_google_file(file_id)
    except:
        existing_content = ""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_lines = []
    if netlify_url:
        new_lines.append(f"{timestamp} - Netlify: {netlify_url}")
    if vercel_url:
        new_lines.append(f"{timestamp} - Vercel: {vercel_url}")
    updated_content = existing_content + "\n" + "\n".join(new_lines)
    upload_google_file(file_id, updated_content)
