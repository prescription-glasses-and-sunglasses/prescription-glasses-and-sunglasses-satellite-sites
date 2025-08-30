import os
import io
import json
import random
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

# ------------------------
# 配置
# ------------------------
FOLDER_IDS = os.environ["GDRIVE_FOLDER_ID"].split(",")
SERVICE_ACCOUNT_JSON = os.environ["GDRIVE_SERVICE_ACCOUNT"]

keywords_file = "keywords.txt"
processed_file_path = "processed_files.json"
siteurl_file = "siteurl.txt"

# ------------------------
# Google Drive API 初始化
# ------------------------
creds = Credentials.from_service_account_info(json.loads(SERVICE_ACCOUNT_JSON))
service = build('drive', 'v3', credentials=creds)

# ------------------------
# 读取缓存
# ------------------------
if os.path.exists(processed_file_path):
    with open(processed_file_path, "r") as f:
        processed_data = json.load(f)
else:
    processed_data = {"fileIds": []}

# ------------------------
# 读取关键词
# ------------------------
with open(keywords_file, "r", encoding="utf-8") as f:
    keywords = [k.strip() for k in f.readlines() if k.strip()]

# ------------------------
# 获取 Google Drive 文件
# ------------------------
def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=100,
        fields="files(id,name,mimeType)"
    ).execute()
    return results.get('files', [])

# ------------------------
# 下载 HTML 或 TXT
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
# 获取所有文件
# ------------------------
all_files = []
print("⏳ 正在从 Google Drive 拉取所有文件列表...")
for folder_id in FOLDER_IDS:
    files = list_files(folder_id)
    all_files.extend(files)

# 筛选新文件
new_files = [f for f in all_files if f['id'] not in processed_data["fileIds"]]
if not new_files:
    print("✅ 没有新的文件需要处理。")
else:
    print(f"发现 {len(new_files)} 个未处理文件。")
    selected_files = random.sample(new_files, min(len(new_files), 30))
    available_keywords = list(keywords)
    keywords_ran_out = False

    for f in selected_files:
        if available_keywords:
            keyword = available_keywords.pop(0)
            safe_name = keyword + ".html"
        else:
            if not keywords_ran_out:
                print("⚠️ 关键词已用完，将使用原始文件名加随机后缀。")
                keywords_ran_out = True
            base_name = os.path.splitext(f['name'])[0]
            sanitized_name = base_name.replace(" ", "-").replace("/", "-")
            random_suffix = str(random.randint(1000, 9999))
            safe_name = f"{sanitized_name}-{random_suffix}.html"

        print(f"正在处理 '{f['name']}' -> '{safe_name}'")

        if f['mimeType'] == 'text/html':
            download_html_file(f['id'], safe_name)
        elif f['mimeType'] == 'text/plain':
            download_txt_file(f['id'], safe_name, f['name'])
        else:
            export_google_doc(f['id'], safe_name)

        processed_data["fileIds"].append(f['id'])

    with open(processed_file_path, "w") as f:
        json.dump(processed_data, f, indent=4)

    with open(keywords_file, "w", encoding="utf-8") as f:
        for keyword in available_keywords:
            f.write(keyword + "\n")

# ------------------------
# 随机部署到 Vercel 和 Netlify
# ------------------------
def deploy_vercel(file_name):
    token = os.environ.get("VERCEL_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}
    files = {'file': open(file_name, 'rb')}
    response = requests.post("https://api.vercel.com/v13/deployments", headers=headers, files=files)
    if response.status_code in [200, 201]:
        url = response.json().get('url')
        print(f"部署到 Vercel: {file_name}")
        return url
    else:
        print(f"❌ Vercel 部署失败: {file_name}")
        return None

def deploy_netlify(file_name):
    token = os.environ.get("NETLIFY_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}
    files = {'file': open(file_name, 'rb')}
    response = requests.post("https://api.netlify.com/api/v1/sites", headers=headers, files=files)
    if response.status_code in [200, 201]:
        url = response.json().get('url')
        print(f"部署到 Netlify: {file_name}")
        return url
    else:
        print(f"❌ Netlify 部署失败: {file_name}")
        return None

html_files = [f for f in os.listdir(".") if f.endswith(".html") and f != "index.html"]
random.shuffle(html_files)
vercel_files = html_files[:10]
netlify_files = html_files[10:20]

site_urls = []

for f in vercel_files:
    url = deploy_vercel(f)
    if url:
        site_urls.append(url)

for f in netlify_files:
    url = deploy_netlify(f)
    if url:
        site_urls.append(url)

if site_urls:
    with open(siteurl_file, "w", encoding="utf-8") as f:
        for u in site_urls:
            f.write(u + "\n")
    print(f"✅ 部署 URL 已保存到 {siteurl_file}")
