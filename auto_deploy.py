import os
import io
import json
import random
import requests
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ------------------------
# Google Drive 认证
# ------------------------
sa_info = json.loads(os.environ.get("GDRIVE_SERVICE_ACCOUNT"))
GDRIVE_FOLDER_IDS = os.environ.get("GDRIVE_FOLDER_ID").split(",")  # 支持多个文件夹

credentials = service_account.Credentials.from_service_account_info(
    sa_info,
    scopes=["https://www.googleapis.com/auth/drive"]
)
service = build('drive', 'v3', credentials=credentials)

# ------------------------
# 下载和处理文件
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
    downloader = MediaIoBaseBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text_content = fh.getvalue().decode('utf-8')
    is_html = text_content.strip().lower().startswith('<!doctype html') or text_content.strip().lower().startswith('<html')
    html_content = text_content if is_html else f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{original_name}</title></head><body><pre>{text_content}</pre></body></html>"
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

def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=100,
        fields="files(id,name,mimeType)"
    ).execute()
    return results.get('files', [])

# ------------------------
# 拉取所有文件
# ------------------------
all_files = []
for folder_id in GDRIVE_FOLDER_IDS:
    all_files.extend(list_files(folder_id))

# ------------------------
# 读取关键词
# ------------------------
with open("keywords.txt", "r", encoding="utf-8") as f:
    keywords = [line.strip() for line in f if line.strip()]

processed_file_path = "processed_files.json"
processed_data = {"fileIds": []}
if os.path.exists(processed_file_path):
    with open(processed_file_path, "r", encoding="utf-8") as f:
        processed_data = json.load(f)

new_files = [f for f in all_files if f['id'] not in processed_data["fileIds"]]
num_to_process = min(len(new_files), 30)
selected_files = random.sample(new_files, num_to_process) if new_files else []

available_keywords = list(keywords)
for f in selected_files:
    if available_keywords:
        keyword = available_keywords.pop(0)
        safe_name = keyword + ".html"
    else:
        base_name = os.path.splitext(f['name'])[0].replace(" ", "-").replace("/", "-")
        random_suffix = str(random.randint(1000, 9999))
        safe_name = f"{base_name}-{random_suffix}.html"

    if f['mimeType'] == 'text/html':
        download_html_file(f['id'], safe_name)
    elif f['mimeType'] == 'text/plain':
        download_txt_file(f['id'], safe_name, f['name'])
    else:
        export_google_doc(f['id'], safe_name)

    processed_data["fileIds"].append(f['id'])

with open(processed_file_path, "w", encoding="utf-8") as f:
    json.dump(processed_data, f, indent=4)

with open("keywords.txt", "w", encoding="utf-8") as f:
    for k in available_keywords:
        f.write(k + "\n")

# ------------------------
# 部署到 Netlify
# ------------------------
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")

html_files = [f for f in os.listdir(".") if f.endswith(".html")]
netlify_files = random.sample(html_files, min(20, len(html_files)))

site_urls = []

def deploy_netlify(file_list):
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    for file in file_list:
        try:
            resp = requests.post("https://api.netlify.com/api/v1/sites", headers=headers, files={"file": open(file, "rb")})
            
            if resp.status_code in [200, 201]:
                site_url = resp.json().get("url")
                if site_url:
                    site_urls.append(site_url)
                    print(f"✅ 部署到 Netlify: {file}")
                else:
                    print(f"❌ Netlify 部署失败: {file} - 未找到 URL")
            else:
                print(f"❌ Netlify 部署失败: {file} - {resp.text}")
        except Exception as e:
            print(f"❌ Netlify 部署异常: {file} - {e}")
        
        print("⏸️ 等待 30 秒以避免频率限制...")
        time.sleep(30)

# 只调用 Netlify 的部署函数
deploy_netlify(netlify_files)

# 保存 siteurl.txt
with open("siteurl.txt", "w", encoding="utf-8") as f:
    for url in site_urls:
        f.write(url + "\n")
print("✅ 部署 URL 已保存到 siteurl.txt")
