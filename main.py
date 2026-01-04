import os
import time
import requests
import zipfile
import io
import datetime
import re
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 基础工具 ====================
def log(message):
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] {message}", flush=True)

def download_silk():
    extract_dir = "silk_ext"
    if os.path.exists(extract_dir): return os.path.abspath(extract_dir)
    try:
        url = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=122.0&acceptformat=crx2,crx3&x=id%3Dajhmfdgkijocedmfjonnpjfojldioehi%26uc"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, stream=True)
        if resp.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                zf.extractall(extract_dir)
            return os.path.abspath(extract_dir)
    except: pass
    return None

# ==================== 核心逻辑 ====================

def pass_full_page_shield(page):
    """处理全屏盾"""
    for _ in range(3):
        if "just a moment" in page.title.lower():
            log("--- [门神] 正在通过全屏盾...")
            iframe = page.ele('css:iframe[src*="cloudflare"]', timeout=2)
            if iframe: 
                iframe.ele('tag:body').click(by_js=True)
                time.sleep(3)
        else:
            return True
    return False

def pass_modal_captcha(modal):
    """
    【复选框特化版】
    根据您的情报，直接寻找 <input type="checkbox">
    """
    log(">>> [弹窗] 正在寻找 Checkbox...")
    
    # 策略 1: 检查 iframe 内部的 input checkbox (最常见的情况)
    # Cloudflare 通常把 checkbox 藏在 iframe 里
    iframe = modal.ele('css:iframe[src*="cloudflare"], iframe[src*="turnstile"]', timeout=5)
    
    if iframe:
        log(">>> [弹窗] 锁定验证码 iframe，查找内部 checkbox...")
        try:
            # 在 iframe 内部找 input
            inner_cb = iframe.ele('css:input[type="checkbox"]', timeout=3)
            if inner_cb:
                log(">>> [弹窗] 🎯 找到 iframe 内的复选框，点击！")
                inner_cb.click(by_js=True)
            else:
                log(">>> [弹窗] iframe 内没找到复选框，尝试点击 iframe 中心...")
                iframe.ele('tag:body').click(by_js=True)
                
            log(">>> [弹窗] 已点击，等待 5 秒变绿...")
            time.sleep(5)
            return True
        except Exception as e:
            log(f"⚠️ iframe 交互失败: {e}")

    # 策略 2: 如果没 iframe，直接在弹窗里找 checkbox
    # 有时候验证码脚本直接加载在当前页面
    direct_cb = modal.ele('css:input[type="checkbox"]', timeout=2)
    if direct_cb:
        log(">>> [弹窗] 🎯 在弹窗层级发现复选框，点击！")
        try:
            direct_cb.click(by_js=True)
            time.sleep(5)
            return True
        except: pass
            
    log(">>> [弹窗] 未能点击到任何复选框")
    return False

def analyze_page_alert(page):
    """解析提示结果"""
    log(">>> [系统] 读取提示信息...")
    
    # 1. 红色警告 (Fail)
    danger_alert = page.ele('css:.alert.alert-danger')
    if danger_alert and danger_alert.states.is_displayed:
        text = danger_alert.text
        log(f"⬇️ 红色提示: {text}")
        
        if "can't renew" in text.lower():
            match = re.search(r'\(in (\d+) day', text)
            days = match.group(1) if match else "?"
            log(f"✅ [结果] 未到期 (等待 {days} 天)")
            return "SUCCESS_TOO_EARLY"
        elif "captcha" in text.lower():
            log("❌ [失败] 验证码未通过！")
            return "FAIL_CAPTCHA" # 触发重试
        else:
            return "FAIL_OTHER"

    # 2. 绿色成功 (Success)
    success_alert = page.ele('css:.alert.alert-success')
    if success_alert and success_alert.states.is_displayed:
        text = success_alert.text
        log(f"⬇️ 绿色提示: {text}")
        log("🎉 [结果] 续期成功！")
        return "SUCCESS"

    return "UNKNOWN"

# ==================== 主程序 ====================
def job():
    ext_path = download_silk()
    
    co = ChromiumOptions()
    co.set_argument('--headless=new')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
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
            log("❌ 配置缺失")
            exit(1)

        # Step 1: 登录
        log(">>> [Step 1] 登录...")
        page.get('https://dashboard.katabump.com/auth/login')
        pass_full_page_shield(page)

        if page.ele('css:input[name="email"]'):
            page.ele('css:input[name="email"]').input(email)
            page.ele('css:input[name="password"]').input(password)
            page.ele('css:button#submit').click()
            page.wait.url_change('login', exclude=True, timeout=20)
        
        # ==================== 重试循环 ====================
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            log(f"\n🚀 [Step 2] 进入服务器页面 (第 {attempt} 次尝试)...")
            page.get(target_url)
            pass_full_page_shield(page)
            
            # 寻找按钮
            renew_btn = None
            for _ in range(5):
                # 使用 data-bs-target 精准定位
                renew_btn = page.ele('css:button[data-bs-target="#renew-modal"]')
                if renew_btn and renew_btn.states.is_displayed: break
                time.sleep(1)

            if renew_btn:
                log(">>> 点击 Renew 按钮...")
                renew_btn.click(by_js=True)
                
                modal = page.ele('css:.modal-content', timeout=10)
                if modal:
                    # 使用新的 Checkbox 策略
                    pass_modal_captcha(modal)
                    
                    # 使用 type="submit" 精准定位
                    confirm_btn = modal.ele('css:button[type="submit"].btn-primary')
                    if confirm_btn:
                        log(">>> 点击 Confirm...")
                        confirm_btn.click(by_js=True)
                        log(">>> 等待响应 (5s)...")
                        time.sleep(5)
                        
                        # 分析结果
                        result = analyze_page_alert(page)
                        
                        if result == "SUCCESS" or result == "SUCCESS_TOO_EARLY":
                            log("🎉 任务完成！")
                            break 
                        
                        if result == "FAIL_CAPTCHA":
                            log("⚠️ 验证码未点中，准备重试...")
                            time.sleep(3)
                            continue
                    else:
                        log("❌ 找不到确认按钮")
                else:
                    log("❌ 弹窗未出")
            else:
                log("⚠️ 未找到按钮，检查是否已有提示...")
                result = analyze_page_alert(page)
                if result == "SUCCESS_TOO_EARLY":
                    break
                else:
                    log("❌ 页面加载异常或无按钮")
            
            if attempt == max_retries:
                log("❌ 已达到最大重试次数，任务失败。")
                exit(1)

    except Exception as e:
        log(f"❌ 异常: {e}")
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
