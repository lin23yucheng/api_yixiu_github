import threading
import os
import tempfile
import shutil
import time
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

        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")

        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-session-crashed-bubble")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")

        temp_profile = tempfile.mkdtemp()
        chrome_options.add_argument(f"--user-data-dir={temp_profile}")
        chrome_options.add_argument(f"--profile-directory=Profile{threading.get_ident()}")

        last_error = None

        def _try_start(source_name, service):
            nonlocal last_error
            try:
                print(f"线程 {threading.get_ident()} 尝试通过 {source_name} 启动浏览器")
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.implicitly_wait(15)
                cls._thread_local.profile_dir = temp_profile
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                if not headless:
                    try:
                        driver.maximize_window()
                        print(f"线程 {threading.get_ident()} 浏览器窗口已最大化")
                    except Exception as e:
                        print(f"线程 {threading.get_ident()} 窗口最大化失败: {str(e)}")
                else:
                    print(f"线程 {threading.get_ident()} 无头模式，跳过窗口最大化")

                print(f"线程 {threading.get_ident()} 浏览器实例创建成功（来源: {source_name}）")
                return driver
            except Exception as e:
                last_error = e
                print(f"线程 {threading.get_ident()} 使用 {source_name} 启动失败: {str(e)}")
                return None

        # 1) 优先本地缓存，避免每次都触发网络下载。
        cached_driver = _find_cached_chromedriver()
        if cached_driver:
            driver = _try_start("本地缓存", Service(cached_driver))
            if driver:
                return driver

        # 2) 缓存不可用时再尝试 webdriver-manager。
        try:
            print(f"线程 {threading.get_ident()} 开始下载/获取 ChromeDriver")
            downloaded_driver = _install_chromedriver_with_retry(max_retries=3)
            if downloaded_driver:
                driver = _try_start("webdriver-manager", Service(downloaded_driver))
                if driver:
                    return driver
        except Exception as e:
            last_error = e
            print(f"线程 {threading.get_ident()} ChromeDriverManager 失败: {str(e)}")

        # 3) 最后兜底 Selenium Manager。
        driver = _try_start("SeleniumManager", Service())
        if driver:
            return driver

        if os.path.exists(temp_profile):
            shutil.rmtree(temp_profile, ignore_errors=True)

        if isinstance(last_error, WebDriverException):
            raise last_error
        raise WebDriverException(f"浏览器实例创建失败: {last_error}")

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
                try:
                    profile_dir = getattr(cls._thread_local, 'profile_dir', None)
                    if profile_dir and os.path.exists(profile_dir):
                        shutil.rmtree(profile_dir, ignore_errors=True)
                        print(f"线程 {threading.get_ident()} 清理临时用户数据目录: {profile_dir}")
                except Exception as e:
                    print(f"线程 {threading.get_ident()} 清理临时用户数据目录异常: {str(e)}")

                if hasattr(cls._thread_local, 'driver'):
                    del cls._thread_local.driver
                if hasattr(cls._thread_local, 'profile_dir'):
                    del cls._thread_local.profile_dir


def _acquire_wdm_lock(lock_file, timeout=120, poll_interval=0.2):
    start = time.time()
    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            return fd
        except FileExistsError:
            if time.time() - start >= timeout:
                return None
            time.sleep(poll_interval)


def _release_wdm_lock(lock_file, fd):
    if fd is None:
        return
    try:
        os.close(fd)
    finally:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except OSError:
                pass


def _find_cached_chromedriver():
    candidates = []
    search_roots = [
        os.environ.get("WDM_CACHE", "").strip(),
        os.path.join(os.path.expanduser("~"), ".wdm"),
        os.path.join(os.getcwd(), ".wdm"),
    ]

    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        for dir_path, _, file_names in os.walk(root):
            for file_name in file_names:
                if file_name in {"chromedriver.exe", "chromedriver"}:
                    driver_path = os.path.join(dir_path, file_name)
                    try:
                        mtime = os.path.getmtime(driver_path)
                    except OSError:
                        continue
                    candidates.append((mtime, driver_path))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _install_chromedriver_with_retry(max_retries=3):
    # 尽量使用本地缓存并缩短网络长时间卡住的概率
    os.environ.setdefault("WDM_LOCAL", "1")
    os.environ.setdefault("WDM_TIMEOUT", "30")
    os.environ.setdefault("WDM_SSL_VERIFY", "0")
    os.environ.setdefault("WDM_LOG_LEVEL", "0")

    lock_file = os.path.join(tempfile.gettempdir(), "yixiu_wdm_install.lock")
    lock_fd = _acquire_wdm_lock(lock_file)
    if lock_fd is None:
        print("等待 ChromeDriver 下载锁超时，继续尝试无锁安装")

    try:
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                start = time.time()
                result_holder = {}

                def _install_worker():
                    try:
                        result_holder["path"] = ChromeDriverManager().install()
                    except Exception as err:
                        result_holder["error"] = err

                install_thread = threading.Thread(target=_install_worker, daemon=True)
                install_thread.start()
                install_thread.join(timeout=45)

                if install_thread.is_alive():
                    raise TimeoutError("ChromeDriver 下载超时(45s)")
                if "error" in result_holder:
                    raise result_holder["error"]

                driver_path = result_holder.get("path")
                elapsed = time.time() - start
                print(f"ChromeDriver 下载/匹配成功，耗时 {elapsed:.1f}s: {driver_path}")
                return driver_path
            except Exception as exc:
                last_error = exc
                print(f"ChromeDriverManager 第 {attempt}/{max_retries} 次失败: {exc}")

                # 网络不可达时快速退出下载重试，转入后续兜底。
                err_text = str(exc).lower()
                if "could not reach host" in err_text or "offline" in err_text:
                    print("检测到网络不可达，停止后续下载重试，转入兜底方案")
                    break

                # 如果外部强制了镜像且镜像异常，则回退到 webdriver-manager 默认源
                if os.environ.get("WDM_CHROMEDRIVER_REPO"):
                    os.environ.pop("WDM_CHROMEDRIVER_REPO", None)
                    print("已移除 WDM_CHROMEDRIVER_REPO，切换 webdriver-manager 默认源重试")

                time.sleep(min(2 * attempt, 5))

        raise last_error
    finally:
        _release_wdm_lock(lock_file, lock_fd)



def get_browser(headless=False):
    """获取当前线程的浏览器实例"""
    return BrowserPool.driver(headless=headless)


def release_browser():
    """释放当前线程的浏览器资源"""
    BrowserPool.cleanup()