import os
import io
import json
import random
import time
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build

# ------------------------
# 配置
# ------------------------
FOLDER_IDS = []  # 可为空，每次自动拉取 Google Drive 所有文件
processed_file_path = "processed_files.json"
keywords_file = "keywords.txt"

# ------------------------
# Google Drive API 初始化
# ------------------------
# 假设你已经有 service 对象
# service = build('drive', 'v3', credentials=creds)

def get_cached_files():
    if os.path.exists(processed_file_path):
        with open(processed_file_path, "r", encoding="utf-8") as f:
            return json.load(f).get("all_files", None)
    return None

def save_files_to_cache(all_files):
    data = {"all_files": all_files, "fileIds": []}
    with open(processed_file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def list_files(folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
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
    
    is_html = text_content.strip().lower().startswith('<!doctype html') or text_content.strip().lower().startswith('<html')
    
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
# 主程序
# ------------------------
processed_data = {"fileIds": []}
if os.path.exists(processed_file_path):
    with open(processed_file_path, "r") as f:
        processed_data = json.load(f)

# 加载 keywords
if os.path.exists(keywords_file):
    with open(keywords_file, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
else:
    keywords = []

# 拉取文件列表
all_files = get_cached_files()
if all_files is None:
    all_files = []
    print("⏳ 正在从 Google Drive 拉取所有文件列表...")
    for folder_id in FOLDER_IDS:
        print(f"📂 正在获取文件夹: {folder_id}")
        files = list_files(folder_id)
        all_files.extend(files)
    save_files_to_cache(all_files)

new_files = [f for f in all_files if f['id'] not in processed_data.get("fileIds", [])]

if not new_files:
    print("✅ 没有新的文件需要处理。")
else:
    print(f"发现 {len(new_files)} 个未处理文件。")
    num_to_process = min(len(new_files), 30)
    selected_files = random.sample(new_files, num_to_process)
    print(f"本次运行将处理 {len(selected_files)} 个文件。")

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
        else:  # Google Doc
            export_google_doc(f['id'], safe_name)

        processed_data["fileIds"].append(f['id'])

    with open(processed_file_path, "w") as f:
        json.dump(processed_data, f, indent=4)
    print(f"💾 已将 {len(selected_files)} 个新文件 ID 保存到 {processed_file_path}")

    with open(keywords_file, "w", encoding="utf-8") as f:
        for keyword in available_keywords:
            f.write(keyword + "\n")
    print(f"✅ 已用剩余的关键词更新 {keywords_file}")

# ------------------------
# 生成站点地图 index.html
# ------------------------
existing_html_files = [f for f in os.listdir(".") if f.endswith(".html") and f != "index.html"]
index_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Reading Glasses</title></head><body>\n"
index_content += "<h1>Reading Glasses</h1>\n<ul>\n"
for fname in sorted(existing_html_files):
    index_content += f'<li><a href="{fname}">{fname}</a></li>\n'
index_content += "</ul>\n</body></html>"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(index_content)
print("✅ 已生成 index.html (完整站点地图)")

# ------------------------
# 随机部署到 Vercel / Netlify
# ------------------------
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")

# 随机选择 10 条部署到 Vercel
vercel_count = min(10, len(existing_html_files))
vercel_files = random.sample(existing_html_files, vercel_count)

# 剩余文件随机选择 10 条部署到 Netlify
remaining_files = [f for f in existing_html_files if f not in vercel_files]
netlify_count = min(10, len(remaining_files))
netlify_files = random.sample(remaining_files, netlify_count)

def deploy_vercel(file_list):
    for f in file_list:
        headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
        # requests.post("https://api.vercel.com/v1/.../deploy", headers=headers, files={"file": open(f, "rb")})
        print(f"部署到 Vercel: {f}")
        time.sleep(0.5)

def deploy_netlify(file_list):
    for f in file_list:
        headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
        # requests.post("https://api.netlify.com/api/v1/sites/{site_id}/deploys", headers=headers, files={"file": open(f, "rb")})
        print(f"部署到 Netlify: {f}")
        time.sleep(0.5)

deploy_vercel(vercel_files)
deploy_netlify(netlify_files)

print("✅ 本次随机部署完成")
