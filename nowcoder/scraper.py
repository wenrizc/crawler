import time
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Response

# 目标 URL
TARGET_URL = (
    "https://www.nowcoder.com/interview/center?entranceType=%E5%AF%BC%E8%88%AA%E6%A0%8F"
)

# 最终数据输出文件
OUTPUT_JSON_FILE = Path("nowcoder_scraped_data.json")


def load_existing_uuids():
    """从现有 JSON 文件中加载已爬取的 UUID 集合"""
    existing_uuids = set()
    existing_data = []
    if OUTPUT_JSON_FILE.exists():
        try:
            with open(OUTPUT_JSON_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                for item in existing_data:
                    if 'uuid' in item:
                        existing_uuids.add(item['uuid'])
            print(f"[*] 从现有文件加载了 {len(existing_uuids)} 个已爬取的 UUID")
        except (json.JSONDecodeError, Exception) as e:
            print(f"[!] 读取现有 JSON 文件失败: {e}")
    return existing_uuids, existing_data


# 请求头
HEADERS = {
    'Host': 'www.nowcoder.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Referer': 'https://www.nowcoder.com/',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}

def scrape():
    """使用 Playwright 筛选分类并收集 UUID，然后使用 Requests 抓取详情页。"""
    # 加载已爬取的 UUID
    existing_uuids, existing_data = load_existing_uuids()
    
    collected_uuids = []
    cookies_for_requests = {}

    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # --- 阶段 1: 筛选分类、监听 API 并收集 UUID (使用 Playwright) ---
        print("============= 阶段 1: 开始筛选分类并收集 UUID =============")
        
        # 导航并等待初始加载
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        print("[*] 页面加载中... 如果出现登录弹窗，请手动关闭。")
        time.sleep(5)
        page.wait_for_load_state("networkidle")
        print("[*] 页面初始加载完成。")
        def handle_response(response: Response):
            if "api/sparta/job-experience/experience/job/list" in response.url:
                try:
                    data = response.json()
                    if data.get("code") == 0:
                        for item in data.get("data", {}).get("records", []):
                            # First try to get uuid from momentData
                            uuid = item.get("momentData", {}).get("uuid")
                            # 跳过已爬取的 UUID
                            if uuid and uuid not in collected_uuids and uuid not in existing_uuids:
                                collected_uuids.append(uuid)
                                print(f"[+] 捕获到新 UUID: {uuid}")
                            elif uuid and uuid in existing_uuids:
                                print(f"[*] 跳过已存在的 UUID: {uuid}")
                except Exception as e:
                    print(f"[*] 解析 API 响应失败: {e}")
        page.on("response", handle_response)
        print("[*] 已启动 API 监听器。")
        print("选择后端开发分类筛选...")
        time.sleep(10)

        # 触发一次滚动，以加载筛选后的第一页数据
        page.mouse.wheel(0, 1000)
        page.wait_for_load_state("networkidle")

        for page_index in range(1, 21):
            print(f"\n--- 正在处理列表页: {page_index}/22 ---")
            page.mouse.wheel(0, 10000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            if page_index == 22:
                break
            try:
                next_button = page.locator("button.btn-next")
                next_button.wait_for(state="visible", timeout=5000)
                next_button.click()
                print("[*] 已点击下一页。")
                page.wait_for_load_state("networkidle")
            except Exception as e:
                print(f"[*] 无法点击下一页或已是最后一页: {e}")
                break
        
        page.remove_listener("response", handle_response)
        print(f"\n[√] 阶段 1 完成！共收集到 {len(collected_uuids)} 个新的 UUID（已排除 {len(existing_uuids)} 个已存在的）。")

        # 提取 cookie 并关闭浏览器
        print("[*] 正在提取 Cookie 用于后续请求...")
        cookies = context.cookies()
        cookies_for_requests = {cookie['name']: cookie['value'] for cookie in cookies}
        browser.close()
        print("[*] Playwright 浏览器已关闭。")

    # --- 阶段 2: 访问详情页并解析数据 (使用 Requests) ---
    print("\n============= 阶段 2: 开始使用 Requests 抓取详情页内容 =============")
    scraped_data = []
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(cookies_for_requests)

    for i, uuid in enumerate(collected_uuids):
        detail_url = f"https://www.nowcoder.com/feed/main/detail/{uuid}"
        print(f"[*] 正在请求 ({i+1}/{len(collected_uuids)}): {detail_url}")
        try:
            response = session.get(detail_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            title_tag = soup.select_one('h1.tw-mb-5.tw-font-medium.tw-text-size-title-lg-pure.tw-text-gray-800')
            title = title_tag.get_text(strip=True) if title_tag else "标题未找到"

            content_tag = soup.select_one('div.feed-content-text.tw-text-gray-800.tw-mb-4.tw-break-all')
            content = str(content_tag) if content_tag else "内容未找到"

            scraped_data.append({
                "uuid": uuid,
                "title": title,
                "content": content,
                "url": detail_url
            })
            print(f"  [+] 标题: {title}")
            time.sleep(2)

        except requests.RequestException as e:
            print(f"  [!] 请求页面 {detail_url} 失败: {e}")
        except Exception as e:
            print(f"  [!] 解析页面 {detail_url} 失败: {e}")

    # --- 保存结果 ---
    if scraped_data:
        # 将新数据放在顶部，旧数据放在后面
        merged_data = scraped_data + existing_data
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, ensure_ascii=False, indent=4)
        print(f"\n[√] 阶段 2 完成！新增 {len(scraped_data)} 条数据，总计 {len(merged_data)} 条，已保存到 {OUTPUT_JSON_FILE.resolve()}")
    else:
        print("\n[!] 未抓取到任何新的详情页数据。")

if __name__ == "__main__":
    scrape()
