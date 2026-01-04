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
    【修正】只点击真正显示的 iframe，防止对着空气点
    """
    # 优先找 Cloudflare 验证码 iframe
    iframe = context_ele.ele('css:iframe[src*="cloudflare"]')
    if not iframe:
        iframe = context_ele.ele('css:iframe[title*="Widget"]')
        
    # 关键修改：必须是可见的 (displayed) 才点
    if iframe and iframe.states.is_displayed:
        log(f">>> [{name}盾] 👁️ 发现可见的验证码，尝试点击...")
        try:
            iframe.ele('tag:body', timeout=2).click(by_js=True)
            log(f">>> [{name}盾] 👆 已点击，等待生效 (5s)...")
            time.sleep(5) 
            return True
        except Exception as e:
            log(f"⚠️ [{name}盾] 点击异常: {e}")
    else:
        # 如果找不到可见的 iframe，说明所谓的拦截可能是误判
        pass
        
    return False

def ensure_page_ready(page):
    """
    【死循环破局版】确保真正进入了 Dashboard
    """
    log("--- [门神] 检查当前页面状态...")
    
    for i in range(1, 10): 
        # 1. 如果能直接找到 Renew 按钮，说明已经进来了，直接放行！
        # 不要管 html 里有没有 captcha 字样，那是误报
        if page.ele('css:button:contains("Renew")'):
            log("--- [门神] 发现 Renew 按钮，通过！")
            return True

        title = page.title.lower()
        
        # 2. 显式拦截：标题是 Just a moment
        if "just a moment" in title or "attention" in title:
            log(f"--- [拦截] 全屏盾阻挡 ({i}/10)，尝试点击...")
            if not handle_captcha(page, "全屏"):
                # 如果没找到验证码却被拦住了，可能是卡了，刷新
                log("--- [操作] 没找到验证码但被拦截，刷新页面...")
                page.refresh()
                time.sleep(5)
            continue
            
        # 3. 隐式拦截：标题正常，但找不到按钮，且有验证码 iframe
        # 只有当 iframe 真实存在且可见时，才认为是拦截
        iframe = page.ele('css:iframe[src*="cloudflare"]')
        if iframe and iframe.states.is_displayed:
             log(f"--- [拦截] 发现页面中有残留验证码 ({i}/10)，清理中...")
             handle_captcha(page, "残留")
             time.sleep(3)
        else:
            # 标题正常，也没验证码 iframe，那可能只是还没加载出来 Renew 按钮
            # 或者根本就没有拦截，只是 html 代码里有 captcha 这个词
            log(f"--- [等待] 页面看似正常，寻找内容中... ({i}/10)")
            
            # 如果等了半天（比如第3次循环了）还是没按钮，刷新一下
            if i % 3 == 0:
                log("--- [操作] 页面卡顿，主动刷新...")
                page.refresh()
                time.sleep(5)
            else:
                time.sleep(2)

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
    
    # 只有当验证码 iframe 真的存在时，才报验证码错误
    iframe = page.ele('css:iframe[src*="cloudflare"]')
    if iframe and iframe.states.is_displayed:
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
        ensure_page_ready(page)
        
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
                
                # 【关键逻辑】强力破门
                # 如果 check_page_ready 返回 True，说明 Renew 按钮已经找到了，或者盾已经彻底没了
                ensure_page_ready(page)
                
                # 寻找主按钮
                renew_btn = page.ele('css:button:contains("Renew")')
                if not renew_btn:
                    log("⚠️ 无 Renew 按钮，可能已续期或页面未加载...")
                    if check_result(page) == "SUCCESS": break
                    
                    # 只有真的找不到按钮，且不是成功状态，才重试
                    log("⚠️ 页面异常，重试...")
                    continue

                # 点击主按钮
                robust_click(renew_btn)
                
                # 等待弹窗
                log(">>> 等待弹窗加载...")
                modal = page.wait.ele_displayed('css:.modal-content', timeout=8)
                
                if modal:
                    # 【核心】处理弹窗里的盾
                    log(">>> [弹窗] 检查内部验证码...")
                    
                    # 先尝试处理验证码
                    handle_captcha(modal, "弹窗")
                    
                    # 再找确认按钮
                    confirm = modal.ele('css:button.btn-primary')
                    if confirm:
                        log(">>> [弹窗] 点击最终确认！")
                        robust_click(confirm)
                        
                        time.sleep(5)
                        if check_result(page) == "SUCCESS":
                            break
                    else:
                        log("⚠️ 没找到确认按钮")
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
