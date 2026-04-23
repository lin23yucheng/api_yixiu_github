import os
import time
import allure
import threading
import configparser
from time import sleep
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from bash.push.client_bash import push_images_auto
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.browser_pool import get_browser, release_browser


@allure.feature("场景：bash坐席分拣流程")
class TestBashUI:
    @classmethod
    def setup_class(cls):

        # 读取配置文件
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')

        # 从浏览器池获取实例 - 启用无头模式
        cls.driver = get_browser(headless=True)

        # 获取当前环境
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        if env not in {"fat", "prod"}:
            raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

        # 从对应环境节读取配置
        env_yixiu_section = f"{env}-yixiu"
        env_bash_section = f"{env}-bash"

        cls.username = config.get(env_bash_section, "myself_account")
        cls.password = config.get(env_bash_section, "myself_password")
        cls.miaiproductcode = config.get(env_yixiu_section, "miai-product-code")

        # 从配置文件获取UI地址
        ui_address_key = "ui_bash_fat" if env == "fat" else "ui_bash_prod"
        cls.ui_bash_fat = config.get(env_bash_section, ui_address_key)

        # 推图线程控制
        cls.push_thread = None
        cls.grpc_mock = None
        cls.push_completed = threading.Event()

    @allure.story("启动推图&分拣图片")
    def test_seat_operation(self):
        with allure.step("步骤1：林禹成账号登录bash系统"):
            # self.driver.get("http://fat-bash-web.svfactory.com:6180/#/signIn")
            self.driver.get(self.ui_bash_fat)  # 使用从配置文件读取的URL
            # 输入账号
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入账号"]'))
            )
            username_input.send_keys(self.username)
            # 输入密码
            password_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入密码"]'))
            )
            password_input.send_keys(self.password)
            # 点击登录按钮
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='登录']"))
            )
            login_button.click()

        with allure.step("步骤2：申请坐席"):
            # 等待进入首页
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'dashboard')]"))
            )

            # 验证初始坐席状态为"我已离席"
            status_text = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//span[@class='status-text']"))
            )
            if status_text.text != "我已离席":
                allure.attach(f"异常状态: {status_text.text}", name="状态错误",
                              attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(f"初始坐席状态应为'我已离席'，实际为: {status_text.text}")
            allure.attach("初始坐席状态: 我已离席", name="状态验证", attachment_type=allure.attachment_type.TEXT)

            # 点击申请坐席按钮
            apply_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'申请坐席')]"))
            )
            apply_button.click()

            # 等待并验证连接消息
            try:
                # 等待"正在建立连接"消息
                connecting_msg = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//p[@class='el-message__content' and contains(text(), '正在建立连接')]"))
                )
                allure.attach("检测到消息: 正在建立连接", name="连接状态", attachment_type=allure.attachment_type.TEXT)

                # 等待"连接建立成功"消息
                success_msg = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//p[@class='el-message__content' and contains(text(), '连接建立成功')]"))
                )
                allure.attach("检测到消息: 连接建立成功", name="连接状态", attachment_type=allure.attachment_type.TEXT)
            except Exception as e:
                allure.attach(f"连接消息验证失败: {str(e)}", name="错误", attachment_type=allure.attachment_type.TEXT)
                raise

            # 验证坐席状态变为"我已坐席"
            def check_seat_status():
                status_text = self.driver.find_element(By.XPATH, "//span[@class='status-text']")
                return status_text.text == "我已坐席"

            # 等待状态变化，最多10秒
            WebDriverWait(self.driver, 10).until(lambda driver: check_seat_status())
            status_text = self.driver.find_element(By.XPATH, "//span[@class='status-text']")
            allure.attach(f"当前坐席状态: {status_text.text}", name="状态验证",
                          attachment_type=allure.attachment_type.TEXT)

            if status_text.text != "我已坐席":
                allure.attach(f"异常状态: {status_text.text}", name="状态错误",
                              attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(f"申请坐席后状态应为'我已坐席'，实际为: {status_text.text}")

        with allure.step("步骤3：启动推图客户端"):
            # push_images_auto 内部已启动线程，这里只保存可控对象
            self.grpc_mock = push_images_auto()
            self.push_thread = getattr(self.grpc_mock, "worker_thread", None)
            allure.attach("推图客户端已启动", name="推图启动", attachment_type=allure.attachment_type.TEXT)

            # 添加等待，确保推图线程初始化完成
            time.sleep(2)  # 等待2秒让推图线程初始化
            allure.attach("推图线程初始化完成", name="推图状态", attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤4：等待图片出现并分拣"):
            empty_counter = 0  # 记录连续为空的次数
            MAX_EMPTY_COUNT = 10  # 监控最长时间

            while True:
                try:
                    # 显式等待产品名称元素出现（10秒超时）
                    product_name = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '//span[@class="product-name"]'))
                    )
                    current_text = product_name.text.strip()

                    # 情况1：检测到配置的产品名称
                    if current_text == self.miaiproductcode:
                        time.sleep(1)  # 显式等待1秒
                        empty_counter = 0  # 重置空状态计数器

                        # 执行点击操作
                        canvas_list = self.driver.find_elements(By.XPATH, '//canvas[@class="upper-canvas "]')
                        if canvas_list:
                            # 点击前截图
                            allure.attach(
                                self.driver.get_screenshot_as_png(),
                                name=f"点击前截图-{time.strftime('%H%M%S')}",
                                attachment_type=allure.attachment_type.PNG
                            )

                            # 使用ActionChains点击
                            ActionChains(self.driver).move_to_element_with_offset(
                                canvas_list[0], 10, 10
                            ).click().perform()

                        continue

                    # 情况2：检测到空文本
                    elif current_text == "":
                        empty_counter += 1
                        # 连续检测到空
                        if empty_counter >= MAX_EMPTY_COUNT:
                            # 执行离席操作
                            leave_button = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.XPATH, '//span[contains(text(),"申请离席")]'))
                            )
                            leave_button.click()
                            sleep(3)
                            allure.attach(f"连续{MAX_EMPTY_COUNT}秒检测到空产品名称，执行离席",
                                          name="离席操作",
                                          attachment_type=allure.attachment_type.TEXT)
                            break

                        # 未达阈值时短暂等待后继续监控
                        time.sleep(1)  # 每次等待1秒
                        continue


                except Exception as e:
                    allure.attach(f"操作异常: {str(e)}", name="错误", attachment_type=allure.attachment_type.TEXT)
                    # 添加异常截图
                    allure.attach(
                        self.driver.get_screenshot_as_png(),
                        name=f"异常截图-{time.strftime('%H%M%S')}",
                        attachment_type=allure.attachment_type.PNG
                    )
                    # 添加页面HTML
                    allure.attach(
                        self.driver.page_source,
                        name="异常时页面HTML",
                        attachment_type=allure.attachment_type.HTML
                    )
                    raise

    @classmethod
    def teardown_class(cls):
        # 先停止推图线程，避免残留后台请求影响下一次执行
        try:
            if cls.grpc_mock is not None:
                cls.grpc_mock.stop()
                worker = getattr(cls.grpc_mock, "worker_thread", None)
                if worker and worker.is_alive():
                    worker.join(timeout=3)
        except Exception as e:
            print(f"停止推图线程时警告: {e}")

        # 仅在浏览器实例存在时执行清理
        if cls.driver and hasattr(cls.driver, 'service') and cls.driver.service.is_connectable():
            try:
                # 清除cookies和本地存储
                cls.driver.delete_all_cookies()
                cls.driver.execute_script("window.localStorage.clear();")
                cls.driver.execute_script("window.sessionStorage.clear();")

                # 导航到空白页释放资源
                cls.driver.get("about:blank")
            except Exception as e:
                print(f"清理浏览器状态时警告: {e}")
                allure.attach(f"清理警告: {str(e)}",
                              name="浏览器清理警告",
                              attachment_type=allure.attachment_type.TEXT)
            finally:
                # 确保最终释放浏览器引用
                release_browser()
        else:
            print("浏览器实例已关闭，跳过清理")
            release_browser()
