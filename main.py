import os
import time
import requests
import zipfile
import io
import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 实时日志工具 ====================
def log(message):
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] {message}", flush=True)

# ==================== 核心逻辑 ====================

def download_and_extract_silk_extension():
    extension_id = "ajhmfdgkijocedmfjonnpjfojldioehi"
    crx_path = "silk.crx"
    extract_dir = "silk_ext"
    
    if os.path.exists(extract_dir) and os.listdir(extract_dir):
        log(f">>> [系统] 插件已就绪")
        return os.path.abspath(extract_dir)
        
    log(">>> [系统] 正在下载 Silk 隐私插件...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    download_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=122.0&acceptformat=crx2,crx3&x=id%3D{extension_id}%26uc"
    
    try:
        resp = requests.get(download_url, headers=headers, stream=True)
        if resp.status_code == 200:
            content = resp.content
            zip_start = content.find(b'PK\x03\x04')
            if zip_start == -1: return None
            with zipfile.ZipFile(io.BytesIO(content[zip_start:])) as zf:
                if not os.path.exists(extract_dir): os.makedirs(extract_dir)
                zf.extractall(extract_dir)
            return os.path.abspath(extract_dir)
        return None
    except: return None

def handle_captcha(context_ele, name=""):
    """
    通用验证码处理器
    核心逻辑：在 context_ele (页面或弹窗) 里找 iframe，找到了就点，点完死等。
    """
    # Cloudflare 验证码通常在 iframe 里
    iframe = context_ele.ele('css:iframe[src*="cloudflare"]')
    if not iframe:
        iframe = context_ele.ele('css:iframe[title*="Widget"]')
        
    if iframe:
        log(f">>> [{name}盾] 👁️ 发现验证码 iframe，准备通过...")
        try:
            # 点击 iframe 内部的 body (触发验证)
            iframe.ele('tag:body', timeout=2).click(by_js=True)
            log(f">>> [{name}盾] 👆 已点击验证框，强制等待验证生效 (6s)...")
            # 这里必须死等，因为这时候页面通常在转圈，脚本不能乱动
            time.sleep(6) 
            return True
        except Exception as e:
            log(f"⚠️ [{name}盾] 点击尝试略过: {e}")
            pass
    return False

def ensure_page_loaded(page):
    """
    【第一道防线】确保进入了页面，而不是卡在全屏盾上
    """
    log("--- [1/2] 检查全屏门神盾...")
    for i in range(10): 
        title = page.title.lower()
        if "just a moment" in title or "attention" in title:
            log(f"--- 还在全屏盾界面，尝试点击... ({i+1})")
            handle_captcha(page, "全屏")
            time.sleep(3)
        else:
            # 检查是否有隐形盾文字
            if "captcha" in page.html.lower():
                 log(f"--- 标题正常但内容显示拦截，尝试点击... ({i+1})")
                 handle_captcha(page, "隐形")
                 time.sleep(3)
            else:
                return True
    return False

def robust_click(ele):
    try:
        ele.scroll.to_see()
        log(f">>> [动作] 点击按钮: {ele.text}")
        ele.click(by_js=True)
        return True
    except:
        return False

def check_result(page):
    log(">>> [检测] 读取结果回显...")
    time.sleep(2)
    full_text = page.html.lower()
    
    if "captcha" in full_text:
        log("❌ 结果: 依然显示验证码拦截 (可能验证未通过)")
        return "FAIL"
    if "can't renew" in full_text or "too early" in full_text:
        log("✅ 结果: 还没到时间 (操作正确)")
        return "SUCCESS"
    if "success" in full_text or "extended" in full_text:
        log("✅ 结果: 续期成功")
        return "SUCCESS"
    
    log("⚠️ 未捕捉到明确结果，假定流程完成")
    return "UNKNOWN"

def job():
    ext_path = download_and_extract_silk_extension()
    co = ChromiumOptions()
    co.set_argument('--headless=new')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--window-size=1920,1080')
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    if ext_path: co.add_extension(ext_path)
    co.auto_port()

    page = ChromiumPage(co)
    page.set.timeouts(15)

    try:
        email = os.environ.get("KB_EMAIL")
        password = os.environ.get("KB_PASSWORD")
        target_url = os.environ.get("KB_RENEW_URL")
        
        if not all([email, password, target_url]): 
            log("❌ Secrets 配置缺失")
            exit(1)

        # ==================== 1. 登录 ====================
        log(">>> [Step 1] 登录...")
        page.get('https://dashboard.katabump.com/auth/login')
        
        # 过第一道盾
        ensure_page_loaded(page)
        
        if page.ele('css:input[name="email"]'):
            log(">>> 输入账号密码...")
            page.ele('css:input[name="email"]').input(email)
            page.ele('css:input[name="password"]').input(password)
            page.ele('css:button[type="submit"]').click()
            page.wait.url_change('login', exclude=True, timeout=15)

        # ==================== 2. 循环尝试 ====================
        for attempt in range(1, 4):
            log(f"\n🚀 [Step 2] 第 {attempt}/3 次尝试...")
            try:
                page.get(target_url)
                
                # 【防线1】刚进页面，先看全屏盾
                if not ensure_page_loaded(page):
                    log("❌ 全屏盾未过，重试...")
                    continue
                
                # 找主按钮
                renew_btn = page.ele('css:button:contains("Renew")')
                if not renew_btn:
                    log("⚠️ 无 Renew 按钮，检查是否已续期...")
                    if check_result(page) == "SUCCESS": break
                    continue

                # 点击主按钮，呼出弹窗
                robust_click(renew_btn)
                
                # 等待弹窗
                log(">>> 等待弹窗加载...")
                modal = page.wait.ele_displayed('css:.modal-content', timeout=8)
                
                if modal:
                    # 【防线2 - 核心】处理弹窗里的“内鬼”盾
                    log(">>> [2/2] 正在处理弹窗内的五秒盾...")
                    
                    # 1. 先找验证码并点击
                    has_captcha = handle_captcha(modal, "弹窗")
                    
                    if has_captcha:
                        log(">>> 验证码已点击，再等 2 秒确保变绿...")
                        time.sleep(2)
                    
                    # 2. 只有处理完验证码，才去找确认按钮
                    confirm = modal.ele('css:button.btn-primary')
                    if confirm:
                        log(">>> 🛡️ 盾已破，点击最终确认！")
                        robust_click(confirm)
                        
                        time.sleep(5) # 等待服务器反应
                        if check_result(page) == "SUCCESS":
                            break
                    else:
                        log("⚠️ 没找到确认按钮，可能被盾挡住了")
                else:
                    log("❌ 弹窗未出现")
            
            except Exception as e:
                log(f"❌ 异常: {e}")
            
            if attempt < 3: 
                log("⏳ 冷却 5 秒...")
                time.sleep(5)

        log("\n🏁 脚本运行结束")

    except Exception as e:
        log(f"❌ 崩溃: {e}")
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
