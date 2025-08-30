import os
import io
import json
import random
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ------------------------
# 配置
# ------------------------
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")
GDRIVE_SERVICE_ACCOUNT_JSON = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ------------------------
# Google Drive API 认证
# ------------------------
service_account_info = json.loads(GDRIVE_SERVICE_ACCOUNT_JSON)
credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

# ------------------------
# 获取文件列表
# ------------------------
def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=100,
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get('files', [])

# ------------------------
# 下载文件
# ------------------------
def download_html_file(file_id, file_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    print(f"✅ 已下载 {file_name}")

def download_txt_file(file_id, file_name, original_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text_content = fh.getvalue().decode('utf-8')

    is_html = text_content.strip().lower().startswith('<!doctype html') or \
              text_content.strip().lower().startswith('<html')

    if is_html:
        html_content = text_content
    else:
        html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{original_name}</title></head><body><pre>{text_content}</pre></body></html>"

    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ TXT 已转换为 HTML: {file_name}")

def export_google_doc(file_id, file_name):
    request = service.files().export_media(fileId=file_id, mimeType='text/html')
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    print(f"✅ Google 文档已导出为 HTML: {file_name}")

# ------------------------
# Vercel 部署
# ------------------------
def deploy_vercel(file_name):
    url = "https://api.vercel.com/v13/deployments"
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
    files = {'file': open(file_name, 'rb')}
    data = {"name": os.path.splitext(file_name)[0]}
    response = requests.post(url, headers=headers, files=files, data=data)
    if response.status_code in (200, 201):
        print(f"✅ 部署到 Vercel: {file_name}")
        return response.json().get("url")
    else:
        print(f"❌ Vercel 部署失败: {file_name} - {response.text}")
        return None

# ------------------------
# Netlify 部署
# ------------------------
def deploy_netlify(file_name):
    url = "https://api.netlify.com/api/v1/sites"
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    # 创建临时站点
    resp = requests.post(url, headers=headers)
    if resp.status_code not in (200, 201):
        print(f"❌ Netlify 创建站点失败: {file_name} - {resp.text}")
        return None
    site_id = resp.json().get("id")
    deploy_url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
    with open(file_name, 'rb') as f:
        files = {'file': f}
        deploy_resp = requests.post(deploy_url, headers=headers, files=files)
    if deploy_resp.status_code in (200, 201):
        print(f"✅ 部署到 Netlify: {file_name}")
        return deploy_resp.json().get("deploy_ssl_url")
    else:
        print(f"❌ Netlify 部署失败: {file_name} - {deploy_resp.text}")
        return None

# ------------------------
# 主程序
# ------------------------
all_files = list_files(GDRIVE_FOLDER_ID)
if not all_files:
    print("❌ 未找到文件，请检查 GDRIVE_FOLDER_ID 或权限")
    exit(1)

# 随机选 10 条文件
num = min(10, len(all_files))
selected_files = random.sample(all_files, num)

# 下载 HTML
for f in selected_files:
    file_id = f['id']
    orig_name = f['name']
    safe_name = f"{orig_name.replace(' ', '-')}.html"
    if f['mimeType'] == 'text/html':
        download_html_file(file_id, safe_name)
    elif f['mimeType'] == 'text/plain':
        download_txt_file(file_id, safe_name, orig_name)
    else:  # Google Doc
        export_google_doc(file_id, safe_name)
    f['safe_name'] = safe_name

# 随机部署到 Vercel / Netlify，保证同一平台不重复
random.shuffle(selected_files)
vercel_files = selected_files[:5]
netlify_files = selected_files[5:10]

site_urls = []

for f in vercel_files:
    url = deploy_vercel(f['safe_name'])
    if url:
        site_urls.append(url)

for f in netlify_files:
    url = deploy_netlify(f['safe_name'])
    if url:
        site_urls.append(url)

# 保存 siteurl.txt
with open("siteurl.txt", "w", encoding="utf-8") as f:
    for url in site_urls:
        f.write(url + "\n")
print("✅ 部署 URL 已保存到 siteurl.txt")
