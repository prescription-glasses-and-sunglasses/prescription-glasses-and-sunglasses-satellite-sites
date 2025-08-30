import os
import io
import json
import random
import shutil
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ------------------------
# 配置
# ------------------------
FOLDER_IDS = os.environ.get("GDRIVE_FOLDER_ID", "").split(",")
SERVICE_ACCOUNT_FILE = os.environ.get("GDRIVE_SERVICE_ACCOUNT", "")
KEYWORDS_FILE = "keywords.txt"
PROCESSED_FILE = "processed_files.json"
DEPLOY_DIR = "deploy_temp"
SITEURL_FILE = "siteurl.txt"

# Vercel / Netlify Token
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")

# ------------------------
# Google Drive 初始化
# ------------------------
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/drive"]
)
service = build('drive', 'v3', credentials=credentials)

# ------------------------
# 缓存
# ------------------------
if os.path.exists(PROCESSED_FILE):
    with open(PROCESSED_FILE, "r") as f:
        processed_data = json.load(f)
else:
    processed_data = {"fileIds": []}

if os.path.exists(KEYWORDS_FILE):
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
else:
    keywords = []

# ------------------------
# 下载文件
# ------------------------
def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=100,
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get('files', [])

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
# 主程序
# ------------------------
all_files = []
for folder_id in FOLDER_IDS:
    all_files.extend(list_files(folder_id))

new_files = [f for f in all_files if f['id'] not in processed_data["fileIds"]]

if not new_files:
    print("✅ 没有新的文件需要处理。")
else:
    print(f"发现 {len(new_files)} 个新文件")
    for f in new_files:
        if keywords:
            keyword = keywords.pop(0)
            safe_name = keyword + ".html"
        else:
            base_name = os.path.splitext(f['name'])[0]
            random_suffix = str(random.randint(1000, 9999))
            safe_name = f"{base_name}-{random_suffix}.html"

        if f['mimeType'] == 'text/html':
            download_html_file(f['id'], safe_name)
        elif f['mimeType'] == 'text/plain':
            download_txt_file(f['id'], safe_name, f['name'])
        else:
            export_google_doc(f['id'], safe_name)

        processed_data["fileIds"].append(f['id'])

    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed_data, f, indent=4)

    with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
        for kw in keywords:
            f.write(kw + "\n")

# ------------------------
# 随机部署
# ------------------------
all_html_files = [f for f in os.listdir('.') if f.endswith('.html')]
vercel_files = random.sample(all_html_files, min(10, len(all_html_files)))
remaining_files = [f for f in all_html_files if f not in vercel_files]
netlify_files = random.sample(remaining_files, min(10, len(remaining_files)))

# 创建临时部署目录
if os.path.exists(DEPLOY_DIR):
    shutil.rmtree(DEPLOY_DIR)
os.makedirs(DEPLOY_DIR)

for f in set(vercel_files + netlify_files):
    shutil.copy(f, DEPLOY_DIR)

# ------------------------
# Vercel 部署
# ------------------------
if vercel_files and VERCEL_TOKEN:
    print("🚀 部署到 Vercel ...")
    result = subprocess.run(
        ["vercel", DEPLOY_DIR, "--prod", "--token", VERCEL_TOKEN, "--confirm"],
        capture_output=True, text=True
    )
    print(result.stdout)
    # 保存 URL
    with open(SITEURL_FILE, "a") as f:
        f.write(result.stdout + "\n")

# ------------------------
# Netlify 部署
# ------------------------
if netlify_files and NETLIFY_TOKEN:
    print("🚀 部署到 Netlify ...")
    result = subprocess.run(
        ["netlify", "deploy", "--dir", DEPLOY_DIR, "--prod", "--auth", NETLIFY_TOKEN],
        capture_output=True, text=True
    )
    print(result.stdout)
    with open(SITEURL_FILE, "a") as f:
        f.write(result.stdout + "\n")

print(f"✅ 部署完成，URL 已保存到 {SITEURL_FILE}")
