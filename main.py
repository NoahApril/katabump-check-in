import os
import time
import requests
import zipfile
import io
from DrissionPage import ChromiumPage, ChromiumOptions

def download_and_extract_silk_extension():
    """
    自动下载并解压 Silk 插件 (用于过 Cloudflare)
    """
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
            # 跳过 CRX 头寻找 Zip 头
            zip_start = content.find(b'PK\x03\x04')
            if zip_start == -1:
                print("❌ 错误：CRX 格式异常")
                return None
            
            with zipfile.ZipFile(io.BytesIO(content[zip_start:])) as zf:
                if not os.path.exists(extract_dir):
                    os.makedirs(extract_dir)
                zf.extractall(extract_dir)
            return os.path.abspath(extract_dir)
        return None
    except Exception as e:
        print(f"⚠️ 插件下载出错: {e}")
        return None

def wait_for_cloudflare(page, timeout=20):
    """等待插件自动过盾"""
    print(f"--- [盾] 等待 Cloudflare ({timeout}s)... ---")
    start = time.time()
    while time.time() - start < timeout:
        if "just a moment" not in page.title.lower():
            print("--- [盾] 通行！ ---")
            return True
        try:
            # 辅助点击
            iframe = page.get_frame('@src^https://challenges.cloudflare.com')
            if iframe: iframe.ele('tag:body').click(by_js=True)
        except: pass
        time.sleep(1)
    return False

def job():
    # --- 1. 准备插件 ---
    ext_path = download_and_extract_silk_extension()
    
    # --- 2. 浏览器配置 ---
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
        # ==================== 步骤 1: 登录 (账号密码) ====================
        print(">>> [1/5] 前往 Katabump 登录页...")
        # 获取账号密码 Secret
        email = os.environ.get("KB_EMAIL")
        password = os.environ.get("KB_PASSWORD")
        
        if not email or not password:
            raise Exception("❌ 请在 GitHub Secrets 配置 KB_EMAIL 和 KB_PASSWORD")

        page.get('https://dashboard.katabump.com/auth/login', retry=3)
        wait_for_cloudflare(page)
        
        # 判断是否需要登录
        if "auth/login" in page.url:
            print(">>> 检测到登录表单，输入账号密码...")
            
            # 定位输入框 (根据 Pterodactyl 面板标准)
            ele_email = page.ele('css:input[name="email"]')
            ele_pass = page.ele('css:input[name="password"]')
            # 定位登录按钮 (通常是 type=submit 的按钮)
            btn_login = page.ele('css:button[type="submit"]')
            
            if ele_email and ele_pass and btn_login:
                ele_email.input(email)
                ele_pass.input(password)
                time.sleep(1)
                print(">>> 点击登录...")
                btn_login.click()
            else:
                page.get_screenshot(path='login_form_missing.jpg')
                raise Exception("❌ 未找到账号/密码输入框")
            
            # 等待跳转
            print(">>> 等待登录跳转...")
            time.sleep(5)
            wait_for_cloudflare(page)
        
        # ==================== 步骤 2: 验证登录 ====================
        if "login" in page.url:
            page.get_screenshot(path='login_fail.jpg')
            print(f"DEBUG HTML: {page.html[:300]}")
            raise Exception("❌ 登录失败：仍停留在登录页 (可能是账号密码错误或验证码拦截)")
        
        print(">>> ✅ 登录成功，进入 Dashboard！")

        # ==================== 步骤 3: 直达服务器 ====================
        target_url = "https://dashboard.katabump.com/servers/edit?id=197288"
        print(f">>> [3/5] 进入服务器: {target_url}")
        page.get(target_url, retry=3)
        page.wait.load_start()
        wait_for_cloudflare(page)
        time.sleep(3)

        # ==================== 步骤 4: 点击续期 ====================
        print(">>> [4/5] 寻找 Renew 按钮...")
        # 查找 Renew, 续期, 或包含 Renew 的按钮
        renew_btn = page.ele('text:Renew') or \
                    page.ele('text:续期') or \
                    page.ele('css:button:contains("Renew")')
        
        if renew_btn:
            # 滚动确保可见
            # page.scroll.to_see(renew_btn)
            renew_btn.click()
            print(">>> 点击 Renew，等待弹窗...")
            time.sleep(3)
            wait_for_cloudflare(page) # 弹窗里可能也有盾
            
            # ==================== 步骤 5: 确认弹窗 ====================
            print(">>> [5/5] 确认续期...")
            modal = page.ele('css:.modal-content')
            if modal:
                # 在弹窗里找确认按钮 (通常是蓝色的 Primary 按钮)
                confirm = modal.ele('text:Renew') or \
                          modal.ele('css:button[type="submit"]') or \
                          modal.ele('css:button.btn-primary')
                
                if confirm:
                    confirm.click()
                    print("🎉🎉🎉 续期成功！任务完成。")
                else:
                    print("❌ 弹窗内未找到确认按钮")
            else:
                print("❌ 未检测到弹窗")
        else:
            print("⚠️ 未找到 Renew 按钮 (可能已续期或布局改变)")
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
