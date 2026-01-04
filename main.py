import os
import time
import requests
import zipfile
import io
from DrissionPage import ChromiumPage, ChromiumOptions

def download_and_extract_silk_extension():
    """自动下载并解压 Silk 插件"""
    extension_id = "ajhmfdgkijocedmfjonnpjfojldioehi"
    crx_path = "silk.crx"
    extract_dir = "silk_ext"
    
    if os.path.exists(extract_dir) and os.listdir(extract_dir):
        print(f">>> [系统] 插件已就绪: {extract_dir}")
        return os.path.abspath(extract_dir)
        
    print(">>> [系统] 正在下载 Silk 隐私插件...")
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

def wait_for_cloudflare(page, timeout=20):
    """等待插件自动过盾"""
    print(f"--- [盾] 等待 Cloudflare ({timeout}s)... ---")
    start = time.time()
    while time.time() - start < timeout:
        # 检测页面标题
        if "just a moment" not in page.title.lower():
            # 额外检查：如果页面里没有 iframe 验证框了，才算真正过盾
            if not page.ele('@src^https://challenges.cloudflare.com'):
                print("--- [盾] 通行！ ---")
                return True
        
        # 尝试辅助点击 (包括弹窗里的 iframe)
        try:
            iframe = page.get_frame('@src^https://challenges.cloudflare.com')
            if iframe: 
                iframe.ele('tag:body').click(by_js=True)
                print("--- [盾] 尝试点击验证框... ---")
        except: pass
        time.sleep(1)
    return False

def job():
    # --- 配置与初始化 ---
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
    try: page.set.timeouts(15)
    except: pass

    try:
        # --- 变量检查 ---
        email = os.environ.get("KB_EMAIL")
        password = os.environ.get("KB_PASSWORD")
        target_url = os.environ.get("KB_RENEW_URL")
        if not all([email, password, target_url]): raise Exception("缺少 Secrets 配置")

        # ==================== 1. 登录 ====================
        print(">>> [1/5] 前往登录页...")
        page.get('https://dashboard.katabump.com/auth/login', retry=3)
        wait_for_cloudflare(page)
        
        if "auth/login" in page.url:
            print(">>> 输入账号密码...")
            page.ele('css:input[name="email"]').input(email)
            page.ele('css:input[name="password"]').input(password)
            time.sleep(1)
            page.ele('css:button[type="submit"]').click()
            print(">>> 等待跳转...")
            time.sleep(5)
            wait_for_cloudflare(page)
        
        if "login" in page.url: raise Exception("登录失败")
        print(">>> ✅ 登录成功！")

        # ==================== 2. 直达服务器 ====================
        print(f">>> [3/5] 进入服务器页面...")
        page.get(target_url, retry=3)
        page.wait.load_start()
        wait_for_cloudflare(page)
        time.sleep(3)

        # ==================== 3. 点击主 Renew 按钮 ====================
        print(">>> [4/5] 寻找主界面 Renew 按钮...")
        # 查找页面上所有的 Renew 按钮
        renew_btn = page.ele('css:button:contains("Renew")') or \
                    page.ele('xpath://button[contains(text(), "Renew")]') or \
                    page.ele('text:Renew')
        
        if renew_btn:
            # 确保点击的是服务器操作区的按钮，而不是导航栏的
            renew_btn.click()
            print(">>> 已点击主按钮，等待弹窗加载...")
            time.sleep(3)
            
            # ==================== 4. 处理弹窗 (根据截图修复) ====================
            print(">>> [5/5] 处理续期弹窗...")
            
            # 1. 弹窗出现后，验证码也会加载，这里必须等待处理
            wait_for_cloudflare(page)
            
            # 2. 定位弹窗
            modal = page.ele('css:.modal-content')
            if modal:
                print(">>> 检测到弹窗，寻找蓝色确认按钮...")
                
                # 【核心修复】精确查找策略：
                # 策略A: 找类名为 btn-primary (蓝色按钮) 的按钮
                # 策略B: 找 type="submit" 的按钮
                # 策略C: 找标签是 button 且文字包含 Renew 的元素
                # 绝对不找 text:Renew (那个是标题)
                confirm_btn = modal.ele('css:button.btn-primary') or \
                              modal.ele('css:button[type="submit"]') or \
                              modal.ele('xpath:.//button[contains(text(), "Renew")]')
                
                if confirm_btn:
                    print(f">>> 找到按钮: {confirm_btn.tag} | 文本: {confirm_btn.text}")
                    if confirm_btn.states.is_enabled:
                        confirm_btn.click()
                        print("🎉🎉🎉 点击确认成功！(请检查是否提示成功)")
                    else:
                        print("⚠️ 按钮处于禁用状态 (Disabled)，可能未到续期时间或验证码未通过")
                else:
                    print("❌ 弹窗内未找到可点击的按钮")
                    # 打印一下弹窗里的按钮信息帮助调试
                    btns = modal.eles('tag:button')
                    for b in btns: print(f"DEBUG: Found button: {b.html}")
            else:
                print("❌ 未检测到弹窗元素 (.modal-content)")
        else:
            print("⚠️ 主界面未找到 Renew 按钮 (可能已续期)")
            page.get_screenshot(path='no_renew.jpg')

    except Exception as e:
        print(f"❌ 运行出错: {e}")
        try: page.get_screenshot(path='error.jpg', full_page=True)
        except: pass
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
