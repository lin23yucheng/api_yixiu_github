import threading
import os
import tempfile
import shutil
from threading import local
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


class BrowserPool:
    _thread_local = local()  # 线程局部存储

    @classmethod
    def driver(cls, headless=False):
        """获取当前线程的浏览器实例（线程安全）"""
        if not hasattr(cls._thread_local, 'driver'):
            cls._thread_local.driver = cls._create_driver(headless=headless)
        return cls._thread_local.driver

    @classmethod
    def _create_driver(cls, headless=False):
        """优化后的浏览器创建方法"""
        print(f"线程 {threading.get_ident()} 开始创建浏览器实例")

        # 添加加速参数
        chrome_options = Options()

        # 如果需要无头模式，添加相应参数
        if headless:
            chrome_options.add_argument("--headless=new")  # 使用新的无头模式

        # 基本性能优化参数
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")

        # 禁用自动化标志
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # 隐藏自动化特征
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-session-crashed-bubble")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")

        # 设置窗口大小和最大化
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")

        # 为每个实例创建独立的临时用户数据目录
        temp_profile = tempfile.mkdtemp()
        chrome_options.add_argument(f"--user-data-dir={temp_profile}")
        chrome_options.add_argument(f"--profile-directory=Profile{threading.get_ident()}")

        # 使用 webdriver-manager 自动管理 ChromeDriver，配置国内镜像
        try:
            print(f"线程 {threading.get_ident()} 开始下载/获取 ChromeDriver")
            # 配置国内镜像源
            os.environ['WDM_CHROMEDRIVER_REPO'] = 'https://cdn.npmmirror.com/binaries/chromedriver'
            service = Service(ChromeDriverManager().install())
            print(f"线程 {threading.get_ident()} ChromeDriver 准备就绪")
        except Exception as e:
            print(f"线程 {threading.get_ident()} ChromeDriverManager 失败，使用默认方式: {str(e)}")
            service = Service()

        # 创建并返回浏览器实例
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.implicitly_wait(15)

            # 移除自动化标记
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # 窗口最大化 - 只在非无头模式下执行
            if not headless:
                try:
                    driver.maximize_window()
                    print(f"线程 {threading.get_ident()} 浏览器窗口已最大化")
                except Exception as e:
                    print(f"线程 {threading.get_ident()} 窗口最大化失败: {str(e)}")
            else:
                print(f"线程 {threading.get_ident()} 无头模式，跳过窗口最大化")

            print(f"线程 {threading.get_ident()} 浏览器实例创建成功")
            return driver
        except WebDriverException as e:
            print(f"线程 {threading.get_ident()} 创建浏览器实例失败 (WebDriverException): {str(e)}")
            raise
        except Exception as e:
            print(f"线程 {threading.get_ident()} 创建浏览器实例失败 (Exception): {str(e)}")
            raise

    @classmethod
    def cleanup(cls):
        """清理当前线程的浏览器资源"""
        if hasattr(cls._thread_local, 'driver'):
            driver = cls._thread_local.driver
            try:
                print(f"线程 {threading.get_ident()} 开始释放浏览器实例")
                driver.quit()
                print(f"线程 {threading.get_ident()} 浏览器实例释放成功")
            except Exception as e:
                print(f"线程 {threading.get_ident()} 释放浏览器异常: {str(e)}")
            finally:
                # 清理临时用户数据目录
                try:
                    if hasattr(driver, 'options'):
                        profile_path = driver.options.arguments
                        for arg in profile_path:
                            if '--user-data-dir=' in arg:
                                profile_dir = arg.split('=')[1]
                                if os.path.exists(profile_dir):
                                    shutil.rmtree(profile_dir, ignore_errors=True)
                                    print(f"线程 {threading.get_ident()} 清理临时用户数据目录: {profile_dir}")
                except Exception as e:
                    print(f"线程 {threading.get_ident()} 清理临时用户数据目录异常: {str(e)}")

                # 删除线程局部存储中的driver引用
                if hasattr(cls._thread_local, 'driver'):
                    del cls._thread_local.driver


def get_browser(headless=False):
    """获取当前线程的浏览器实例"""
    return BrowserPool.driver(headless=headless)


def release_browser():
    """释放当前线程的浏览器资源"""
    BrowserPool.cleanup()