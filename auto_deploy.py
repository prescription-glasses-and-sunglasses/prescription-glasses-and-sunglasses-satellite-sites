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
# GitHub repository info
# ------------------------
owner_repo = os.environ.get("GITHUB_REPOSITORY")
if not owner_repo:
    print("❌ 未找到 GITHUB_REPOSITORY 环境变量")
    sys.exit(1)

GITHUB_USERNAME, GITHUB_REPO = owner_repo.split("/")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # Actions 默认提供
if not GITHUB_TOKEN:
    print("❌ 未找到 GITHUB_TOKEN 环境变量")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# ------------------------
# Google Drive service account
# ------------------------
service_account_info = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
if not service_account_info:
    print("❌ 未找到 GDRIVE_SERVICE_ACCOUNT 环境变量")
    sys.exit(1)

try:
    service_account_info = json.loads(service_account_info)
except json.JSONDecodeError:
    print("❌ GDRIVE_SERVICE_ACCOUNT JSON解析失败")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# ------------------------
# Google Drive folder IDs
# ------------------------
folder_ids_str = os.environ.get("GDRIVE_FOLDER_ID")
if not folder_ids_str:
    print("❌ 未找到 GDRIVE_FOLDER_ID 环境变量")
    sys.exit(1)

FOLDER_IDS = [fid.strip() for fid in folder_ids_str.split(",") if fid.strip()]

# ------------------------
# keywords
# ------------------------
keywords_file = "keywords.txt"
keywords = []
if os.path.exists(keywords_file):
    with open(keywords_file, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

# ------------------------
# processed files cache
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
                if last_updated and (time.time() - last_updated < CACHE_EXPIRY_HOURS*3600):
                    print("✅ 缓存未过期，从本地加载文件列表")
                    return cache_data.get("files", [])
        except:
            pass
    return None

def save_files_to_cache(files):
    cache_data = {"last_updated": time.time(), "files": files}
    with open(cache_file_path, "w") as f:
        json.dump(cache_data, f, indent=4)

# ------------------------
# list files from folder
# ------------------------
def list_files(folder_id):
    all_files = []
    page_token = None
    query = f"'{folder_id}' in parents and (" \
            "mimeType='text/html' or " \
            "mimeType='text/plain' or " \
            "mimeType='application/vnd.google-apps.document')"
    while True:
        results = service.files().list(
            q=query,
            pageSize=1000,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        items = results.get('files', [])
        all_files.extend(items)
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    print(f"📂 文件夹 {folder_id} 共找到 {len(all_files)} 个文件")
    return all_files

# ------------------------
# download/export files
# ------------------------
def download_html_file(file_id, file_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

def download_txt_file(file_id, file_name, original_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text_content = fh.getvalue().decode('utf-8')
    is_html = text_content.strip().lower().startswith('<!doctype html') or text_content.strip().lower().startswith('<html')
    if is_html:
        html_content = text_content
    else:
        html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{original_name}</title></head><body><pre>{text_content}</pre></body></html>"
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(html_content)

def export_google_doc(file_id, file_name):
    request = service.files().export_media(fileId=file_id, mimeType='text/html')
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

# ------------------------
# 获取文件列表
# ------------------------
all_files = get_cached_files()
if all_files is None:
    all_files = []
    for fid in FOLDER_IDS:
        all_files.extend(list_files(fid))
    save_files_to_cache(all_files)

new_files = [f for f in all_files if f['id'] not in processed_data["fileIds"]]

# ------------------------
# 处理文件
# ------------------------
if new_files:
    print(f"发现 {len(new_files)} 个新文件")
    num_to_process = min(len(new_files), 30)
    selected_files = random.sample(new_files, num_to_process)
    available_keywords = list(keywords)
    for f in selected_files:
        if available_keywords:
            keyword = available_keywords.pop(0)
            safe_name = keyword + ".html"
        else:
            base_name = os.path.splitext(f['name'])[0].replace(" ", "-").replace("/", "-")
            random_suffix = str(random.randint(1000,9999))
            safe_name = f"{base_name}-{random_suffix}.html"
        if f['mimeType']=='text/html':
            download_html_file(f['id'], safe_name)
        elif f['mimeType']=='text/plain':
            download_txt_file(f['id'], safe_name, f['name'])
        else:
            export_google_doc(f['id'], safe_name)
        processed_data["fileIds"].append(f['id'])
    with open(processed_file_path, 'w') as f:
        json.dump(processed_data, f, indent=4)
    with open(keywords_file, 'w', encoding='utf-8') as f:
        for k in available_keywords:
            f.write(k+'\n')

# ------------------------
# 生成 sitemap
# ------------------------
html_files = [f for f in os.listdir(".") if f.endswith(".html") and f!="index.html"]
index_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Site Map</title></head><body><h1>Site Map</h1><ul>\n"
for fname in sorted(html_files):
    index_content += f'<li><a href="{fname}">{fname}</a></li>\n'
index_content += "</ul></body></html>"
with open("index.html","w",encoding='utf-8') as f:
    f.write(index_content)

# ------------------------
# 添加随机内部链接
# ------------------------
for fname in html_files:
    try:
        with open(fname,'r',encoding='utf-8',errors='replace') as f:
            content = f.read()
        content = re.sub(r"<footer>.*?</footer>", "", content, flags=re.DOTALL|re.IGNORECASE)
        other_files = [x for x in html_files if x!=fname]
        num_links = min(len(other_files), random.randint(4,6))
        if num_links>0:
            random_links = random.sample(other_files, num_links)
            links_html = "<footer><ul>\n" + "\n".join([f'<li><a href="{x}">{x}</a></li>' for x in random_links]) + "\n</ul></footer>"
            content = re.sub(r"</body>\s*</html>.*$", "", content, flags=re.IGNORECASE)
            content = content.strip() + "\n" + links_html + "</body></html>"
        with open(fname,'w',encoding='utf-8') as f:
            f.write(content)
    except:
        pass

# ------------------------
# GitHub API 上传文件
# ------------------------
def github_upload_file(file_path):
    with open(file_path,'rb') as f:
        content = f.read()
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{file_path}"
    data = {
        "message": f"Auto update {file_path}",
        "content": base64.b64encode(content).decode('utf-8')
    }
    r = requests.put(url, headers=headers, data=json.dumps(data))
    if r.status_code in [200,201]:
        print(f"✅ 上传成功: {file_path}")
    else:
        print(f"❌ 上传失败: {file_path}, {r.status_code}, {r.text}")

for fname in html_files + ["index.html"]:
    github_upload_file(fname)

# ------------------------
# 调用 Netlify / Vercel 部署（可选）
# ------------------------
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID")
if NETLIFY_TOKEN and NETLIFY_SITE_ID:
    r = requests.post(f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/builds",
                      headers={"Authorization":f"Bearer {NETLIFY_TOKEN}"})
    if r.status_code==201:
        print("✅ Netlify 构建触发成功")
    else:
        print(f"❌ Netlify 构建失败: {r.text}")

VERCEL_TOKEN = os.environ.get("
