import os
import io
import json
import random
import requests
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ------------------------
# 配置
# ------------------------
GDRIVE_SERVICE_ACCOUNT = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
GDRIVE_FOLDER_IDS = os.environ.get("GDRIVE_FOLDER_IDS", "").split(",")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")

KEYWORDS_FILE = "keywords.txt"
SITEURL_FILE = "siteurl.txt"
PROCESSED_FILE = "processed_files.json"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ------------------------
# Google Drive 初始化
# ------------------------
credentials = service_account.Credentials.from_service_account_info(
    json.loads(GDRIVE_SERVICE_ACCOUNT), scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=100,
        fields="files(id,name,mimeType)"
    ).execute()
    return results.get('files', [])

def download_file(file_id, filename):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(filename, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    print(f"✅ 已下载 {filename}")

def export_google_doc(file_id, filename):
    request = service.files().export_media(fileId=file_id, mimeType='text/html')
    fh = io.FileIO(filename, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    print(f"✅ Google 文档导出为 HTML: {filename}")

def txt_to_html(file_id, filename, original_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text_content = fh.getvalue().decode('utf-8')
    html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{original_name}</title></head><body><pre>{text_content}</pre></body></html>"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ TXT 已转换为 HTML: {filename}")

# ------------------------
# 加载关键词
# ------------------------
if os.path.exists(KEYWORDS_FILE):
    with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
        keywords = [line.strip() for line in f if line.strip()]
else:
    keywords = []

# ------------------------
# 加载已处理文件
# ------------------------
if os.path.exists(PROCESSED_FILE):
    with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
        processed_data = json.load(f)
else:
    processed_data = {"fileIds": []}

# ------------------------
# 拉取 Google Drive 文件
# ------------------------
all_files = []
for folder_id in GDRIVE_FOLDER_IDS:
    files = list_files(folder_id)
    all_files.extend(files)

new_files = [f for f in all_files if f['id'] not in processed_data["fileIds"]]

if not new_files:
    print("✅ 没有新文件")
else:
    print(f"发现 {len(new_files)} 个新文件")
    selected_files = random.sample(new_files, min(len(new_files), 30))
    available_keywords = keywords.copy()
    for f in selected_files:
        if available_keywords:
            keyword = available_keywords.pop(0)
            safe_name = f"{keyword}.html"
        else:
            base_name = os.path.splitext(f['name'])[0].replace(" ", "-").replace("/", "-")
            safe_name = f"{base_name}-{random.randint(1000,9999)}.html"

        print(f"处理文件: {f['name']} -> {safe_name}")

        if f['mimeType'] == 'text/html':
            download_file(f['id'], safe_name)
        elif f['mimeType'] == 'text/plain':
            txt_to_html(f['id'], safe_name, f['name'])
        else:
            export_google_doc(f['id'], safe_name)

        processed_data["fileIds"].append(f['id'])

    # 保存处理记录
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, indent=2)

    # 更新剩余关键词
    with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
        for k in available_keywords:
            f.write(k + "\n")

# ------------------------
# 随机部署到 Vercel / Netlify
# ------------------------
html_files = [f for f in os.listdir(".") if f.endswith(".html") and f != "index.html"]
random.shuffle(html_files)

vercel_files = html_files[:10]
netlify_files = html_files[10:20]

def deploy_vercel(file_list):
    urls = []
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}", "Content-Type": "application/json"}
    for fname in file_list:
        data = {
            "name": f"auto-{random.randint(10000,99999)}",
            "files": {fname: {"file": open(fname, 'r', encoding='utf-8').read()}}
        }
        # 调用 Vercel Deploy API
        resp = requests.post("https://api.vercel.com/v13/deployments", headers=headers, json=data)
        if resp.status_code == 200:
            url = resp.json().get("url")
            print(f"部署到 Vercel: {fname} -> {url}")
            urls.append(f"Vercel: {url}")
        else:
            print(f"❌ Vercel 部署失败: {fname} -> {resp.status_code}")
    return urls

def deploy_netlify(file_list):
    urls = []
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    for fname in file_list:
        # 创建新站点
        site_resp = requests.post("https://api.netlify.com/api/v1/sites", headers=headers)
        if site_resp.status_code != 200:
            print(f"❌ Netlify 创建站点失败: {fname} -> {site_resp.status_code}")
            continue
        site_id = site_resp.json()['id']
        # 上传文件
        upload_resp = requests.put(f"https://api.netlify.com/api/v1/sites/{site_id}/files/{fname}",
                                   headers=headers, data=open(fname, 'rb'))
        if upload_resp.status_code in (200, 201):
            url = site_resp.json()['ssl_url']
            print(f"部署到 Netlify: {fname} -> {url}")
            urls.append(f"Netlify: {url}")
        else:
            print(f"❌ Netlify 上传失败: {fname} -> {upload_resp.status_code}")
    return urls

site_urls = []
site_urls.extend(deploy_vercel(vercel_files))
site_urls.extend(deploy_netlify(netlify_files))

# 写入 siteurl.txt
with open(SITEURL_FILE, 'a', encoding='utf-8') as f:
    for u in site_urls:
        f.write(u + "\n")
print(f"✅ 已将部署 URL 写入 {SITEURL_FILE}")
