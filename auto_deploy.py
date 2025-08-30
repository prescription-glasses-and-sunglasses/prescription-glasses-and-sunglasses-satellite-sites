import os
import json
import tempfile
import shutil
import requests
import random
import zipfile
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ------------------------
# 配置
# ------------------------
GDRIVE_SERVICE_ACCOUNT = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
PROJECT_TEMP_DIR = "publish_site"

# ------------------------
# Google Drive 初始化
# ------------------------
credentials = service_account.Credentials.from_service_account_info(
    json.loads(GDRIVE_SERVICE_ACCOUNT)
)
service = build('drive', 'v3', credentials=credentials)

def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=100,
        fields="files(id,name,mimeType)"
    ).execute()
    return results.get('files', [])

def download_html_file(file_id, file_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    print(f"✅ 下载完成: {file_name}")

def download_txt_file(file_id, file_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text_content = fh.getvalue().decode('utf-8')
    html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{file_name}</title></head><body><pre>{text_content}</pre></body></html>"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ TXT 转 HTML: {file_name}")

# ------------------------
# 创建临时目录
# ------------------------
def prepare_temp_dir():
    if os.path.exists(PROJECT_TEMP_DIR):
        shutil.rmtree(PROJECT_TEMP_DIR)
    os.makedirs(PROJECT_TEMP_DIR, exist_ok=True)

# ------------------------
# 生成 index.html
# ------------------------
def generate_index(dir_path, files):
    index_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Site</title></head><body>\n<h1>Site</h1>\n<ul>\n"
    for fname in sorted(files):
        index_content += f'<li><a href="{fname}">{fname}</a></li>\n'
    index_content += "</ul>\n</body></html>"
    with open(os.path.join(dir_path, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_content)

# ------------------------
# 部署到 Netlify
# ------------------------
def deploy_netlify(file_paths):
    headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    r = requests.post("https://api.netlify.com/api/v1/sites", headers=headers)
    site = r.json()
    site_id = site["id"]
    site_url = site["ssl_url"]

    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            r2 = requests.put(
                f"https://api.netlify.com/api/v1/sites/{site_id}/files/{file_name}",
                headers=headers,
                data=f
            )
            if r2.status_code not in [200, 201]:
                print(f"❌ Netlify 上传失败: {file_name} - {r2.text}")
    print(f"✅ Netlify 部署完成: {site_url}")
    return site_url

# ------------------------
# 部署到 Vercel
# ------------------------
def deploy_vercel(file_paths):
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
    project_name = f"site-{random.randint(1000,9999)}"

    data = {"name": project_name}
    r = requests.post("https://api.vercel.com/v9/projects", headers=headers, json=data)
    project = r.json()
    project_id = project["id"]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            zipf.write(file_path, os.path.basename(file_path))
    zip_buffer.seek(0)

    upload_url = f"https://api.vercel.com/v13/deployments?projectId={project_id}"
    files = {'file': ('source.zip', zip_buffer)}
    r2 = requests.post(upload_url, headers=headers, files=files)
    if r2.status_code not in [200, 201]:
        print(f"❌ Vercel 上传失败: {r2.text}")
        return None

    deploy_info = r2.json()
    url = deploy_info.get("url", f"{project_name}.vercel.app")
    print(f"✅ Vercel 部署完成: https://{url}")
    return f"https://{url}"

# ------------------------
# 主流程
# ------------------------
prepare_temp_dir()

# 拉取 Google Drive 文件
all_files = list_files(GDRIVE_FOLDER_ID)
html_files = []

for f in all_files:
    safe_name = f['name'].replace(" ", "_")
    full_path = os.path.join(PROJECT_TEMP_DIR, safe_name)
    if f['mimeType'] == 'text/html':
        download_html_file(f['id'], full_path)
    elif f['mimeType'] == 'text/plain':
        download_txt_file(f['id'], full_path)
    html_files.append(full_path)

# 随机选择 10 条文件
num_to_deploy = min(10, len(html_files))
selected_files = random.sample(html_files, num_to_deploy)

# 分配 Vercel / Netlify（不重复）
random.shuffle(selected_files)
half = len(selected_files) // 2
netlify_files = selected_files[:half]
vercel_files = selected_files[half:]

site_urls = []
if netlify_files:
    site_urls.append(deploy_netlify(netlify_files))
if vercel_files:
    site_urls.append(deploy_vercel(vercel_files))

# 保存 URL
with open("siteurl.txt", "w", encoding="utf-8") as f:
    for url in site_urls:
        f.write(url + "\n")
print("✅ 所有部署 URL 已保存到 siteurl.txt")
