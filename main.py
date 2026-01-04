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

def click_captcha_if_present(context_ele, name=""):
    """
    通用验证码处理函数
    context_ele: 可以是 page（全页）也可以是 modal（弹窗）
    """
    # 寻找 iframe
    iframe = context_ele.ele('css:iframe[src*="cloudflare"]')
    if not iframe:
        iframe = context_ele.ele('css:iframe[title*="Widget"]')
        
    if iframe:
        log(f">>> [{name}盾] 发现验证码，尝试点击...")
        try:
            # 点击 iframe 内部的 body
            iframe.ele('tag:body', timeout=2).click(by_js=True)
            log(f">>> [{name}盾] 已点击，等待变绿 (5s)...")
            time.sleep(5) # 给足时间让它转圈
            return True
        except:
            pass
    return False

def ensure_page_access(page):
    """
    【死磕模式】确保真正进入了页面，而不是停在 Cloudflare 盾上
    """
    log("--- [门神] 正在检查是否真正进入页面...")
    for i in range(10): # 最多尝试 10 次检查
        title = page.title.lower()
        
        # 如果标题包含 just a moment，说明还在盾上
        if "just a moment" in title or "attention" in title:
            log(f"--- [门神] 还在盾界面 (Just a moment)，尝试破盾... ({i+1}/10)")
            click_captcha_if_present(page, "全页")
            time.sleep(3)
        else:
            # 检查页面里有没有验证码拦截的文字
            html = page.html.lower()
            if "captcha" in html or "challenge" in html:
                 log(f"--- [门神] 标题正常但内容被拦截，尝试破盾... ({i+1}/10)")
                 click_captcha_if_present(page, "隐形")
                 time.sleep(3)
            else:
                log("--- [门神] 通行成功！")
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
    log(">>> [检测] 分析结果...")
    time.sleep(2)
    full_text = page.html.lower()
    
    if "captcha" in full_text:
        log("❌ 结果: 验证码拦截")
        return "FAIL"
    if "can't renew" in full_text or "too early" in full_text:
        log("✅ 结果: 还没到时间")
        return "SUCCESS"
    if "success" in full_text or "extended" in full_text:
        log("✅ 结果: 续期成功")
        return "SUCCESS"
    
    log("⚠️ 未捕捉到明确结果")
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
    
    # 恢复正常加载模式，防止漏加载 iframe
    # co.set_load_mode('normal') 

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
        
        # 确保能看见登录框
        ensure_page_access(page)
        
        if page.ele('css:input[name="email"]'):
            log(">>> 输入账号密码...")
            page.ele('css:input[name="email"]').input(email)
            page.ele('css:input[name="password"]').input(password)
            page.ele('css:button[type="submit"]').click()
            
            log(">>> 等待跳转...")
            page.wait.url_change('login', exclude=True, timeout=15)

        # ==================== 2. 循环尝试 (3次) ====================
        for attempt in range(1, 4):
            log(f"\n🚀 [Step 2] 第 {attempt}/3 次续期尝试...")
            try:
                page.get(target_url)
                
                # 【第一关】进门前，必须把全页盾给破了
                if not ensure_page_access(page):
                    log("❌ 无法突破进门盾，重试...")
                    continue
                
                # 寻找主界面 Renew 按钮
                renew_btn = page.ele('css:button:contains("Renew")')
                if not renew_btn:
                    log("⚠️ 未找到 Renew 按钮，检查状态...")
                    if check_result(page) == "SUCCESS": break
                    continue

                # 点击主 Renew
                robust_click(renew_btn)
                
                # 等待弹窗
                log(">>> 等待弹窗弹出...")
                modal = page.wait.ele_displayed('css:.modal-content', timeout=8)
                
                if modal:
                    # 【第二关 - 核心修复】弹窗里的验证码
                    # 在点击确认之前，必须先点弹窗里的盾！
                    log(">>> [流程] 检查弹窗内是否有验证码...")
                    click_captcha_if_present(modal, "弹窗内")
                    
                    # 再次检查，确保它是绿的（有时候需要点两次）
                    # 这里加一个等待，确保验证生效
                    
                    confirm = modal.ele('css:button.btn-primary')
                    if confirm:
                        log(">>> [流程] 验证处理完毕，点击最终确认...")
                        robust_click(confirm)
                        
                        time.sleep(5) # 等待提交结果
                        if check_result(page) == "SUCCESS":
                            break
                    else:
                        log("⚠️ 确认按钮没找到")
                else:
                    log("❌ 弹窗未出现")
            
            except Exception as e:
                log(f"❌ 异常: {e}")
            
            if attempt < 3: 
                log("⏳ 休息 5 秒...")
                time.sleep(5)

        log("\n🏁 脚本运行结束")

    except Exception as e:
        log(f"❌ 崩溃: {e}")
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
