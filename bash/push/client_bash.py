"""
bash推图(手动/自动)
"""
import configparser

from bash.push.log import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from google.protobuf.json_format import MessageToDict
import os
import time
import json
import grpc
import random
import traceback
import threading
import bash.push.bash_pb2 as grpc_api
import bash.push.bash_pb2_grpc as grpc_control
from bash.push.log import LogType, log

# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
config_path = os.path.join(project_root, 'config', 'env_config.ini')
config = configparser.ConfigParser()
config.read(config_path, encoding='utf-8')

# 获取当前环境并读取对应的picture_num
env = config.get("environment", "execution_env", fallback="").strip().lower()
if env not in {"fat", "prod"}:
    raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")
env_bash_section = f"{env}-bash"
picture_num = int(config.get(env_bash_section, 'picture_num'))


# 常量定义
class Constants:
    IS_CROP = 2
    DETECTION_AREA_TYPE = 2
    SYSTEM_TYPE = 1
    DEFAULT_ADDRESS_NO = 1  # GRPC请求编号
    DEFAULT_THREADS = 1  # 线程数
    DEFAULT_LOOPS = picture_num  # 循环数


# 生成随机的前三位数字 (1000-9999)
random_part1 = random.randint(1000, 1100)
random_part2 = random.randint(2000, 2100)
random_part3 = random.randint(1, 5)


# 路径工具函数
def get_relative_path(*sub_paths):
    """获取相对于当前文件的路径"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, '..', *sub_paths)


# 资源加载器（单例模式）
class ResourceLoader:
    _certs = None
    _params = None
    _config = None

    @classmethod
    def get_certs(cls):
        """加载SSL证书"""
        if cls._certs is None:
            key_path = get_relative_path('crt', 'client.key')
            crt_path = get_relative_path('crt', 'client.crt')
            ca_path = get_relative_path('crt', 'ca.crt')

            cls._certs = {
                'private_key': open(key_path, 'rb').read(),
                'certificate_chain': open(crt_path, 'rb').read(),
                'root_certificates': open(ca_path, 'rb').read()
            }
        return cls._certs

    @classmethod
    def get_params(cls):
        """加载参数配置"""
        if cls._params is None:
            params_path = get_relative_path('json', 'params_data.json')
            with open(params_path, encoding='utf-8') as f:
                cls._params = json.load(f)
        return cls._params

    @classmethod
    def get_config(cls, config_data=None):
        """加载主配置"""
        if cls._config is None or config_data is not None:
            if config_data:
                cls._config = config_data
            else:
                config_path = get_relative_path('json', 'config.json')
                with open(config_path, encoding='utf-8') as f:
                    cls._config = json.load(f)
        return cls._config

    @classmethod
    def get_dynamic_params(cls):
        """动态获取参数：从accessToken.txt读取token，从配置文件读取miai-product-code和device_no"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # 1. 读取accessToken.txt
        token_path = os.path.join(project_root, 'testdata', 'accessToken.txt')
        access_token = ""
        if os.path.exists(token_path):
            with open(token_path, 'r') as f:
                access_token = f.read().strip()
            log(f"成功读取Token文件: {token_path}", LogType.INFO)
        else:
            log(f"Token文件不存在: {token_path}", LogType.WARNING)

        # 2. 读取配置文件获取miai-product-code和device_no
        config_path = os.path.join(project_root, 'config', 'env_config.ini')
        miai_product_code = ""
        device_no = ""
        if os.path.exists(config_path):
            config = configparser.ConfigParser()
            config.read(config_path, encoding='utf-8')

            # 获取当前环境
            env = config.get("environment", "execution_env", fallback="").strip().lower()
            if env not in {"fat", "prod"}:
                raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

            # 从对应环境节读取
            env_section = f"{env}-yixiu"
            try:
                miai_product_code = config.get(env_section, 'miai-product-code')
                log(f"成功读取miai-product-code: {miai_product_code}", LogType.INFO)
            except configparser.NoOptionError:
                log(f"配置文件{env_section}中缺少miai-product-code字段", LogType.WARNING)
            try:
                device_no = config.get(env_section, 'device_no')
                log(f"成功读取device_no: {device_no}", LogType.INFO)
            except configparser.NoOptionError:
                log(f"配置文件{env_section}中缺少device_no字段", LogType.WARNING)
        else:
            log(f"配置文件不存在: {config_path}", LogType.WARNING)

        # 3. 获取原始参数并更新
        params = cls.get_params()
        params["access_token"] = access_token
        params["device_no"] = device_no
        params["product_name"] = miai_product_code

        # 记录更新后的参数
        log(
            f"动态参数更新: access_token={access_token[:10]}..., device_no={device_no}, product_name={miai_product_code}",
            LogType.INFO
        )

        return params

    @classmethod
    def update_params_json(cls):
        """更新params_data.json文件：从accessToken.txt读取token，从配置文件读取miai-product-code和device_no"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # 1. 读取accessToken.txt
        token_path = os.path.join(project_root, 'testdata', 'accessToken.txt')
        access_token = ""
        if os.path.exists(token_path):
            with open(token_path, 'r') as f:
                access_token = f.read().strip()
            log(f"成功读取Token文件: {token_path}", LogType.INFO)
        else:
            log(f"Token文件不存在: {token_path}", LogType.WARNING)

        # 2. 读取配置文件获取miai-product-code和device_no
        config_path = os.path.join(project_root, 'config', 'env_config.ini')
        miai_product_code = ""
        device_no = ""
        if os.path.exists(config_path):
            config = configparser.ConfigParser()
            config.read(config_path, encoding='utf-8')

            # 获取当前环境
            env = config.get("environment", "execution_env", fallback="").strip().lower()
            if env not in {"fat", "prod"}:
                raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

            # 从对应环境节读取
            env_section = f"{env}-yixiu"
            try:
                miai_product_code = config.get(env_section, 'miai-product-code')
                log(f"成功读取miai-product-code: {miai_product_code}", LogType.INFO)
            except configparser.NoOptionError:
                log(f"配置文件{env_section}中缺少miai-product-code字段", LogType.WARNING)
            try:
                device_no = config.get(env_section, 'device_no')
                log(f"成功读取device_no: {device_no}", LogType.INFO)
            except configparser.NoOptionError:
                log(f"配置文件{env_section}中缺少device_no字段", LogType.WARNING)
        else:
            log(f"配置文件不存在: {config_path}", LogType.WARNING)

        # 3. 获取原始参数路径
        params_path = get_relative_path('json', 'params_data.json')

        # 4. 读取现有JSON内容
        try:
            with open(params_path, 'r', encoding='utf-8') as f:
                params = json.load(f)
        except Exception as e:
            log(f"读取参数文件失败: {e}", LogType.ERROR)
            return False

        # 5. 更新关键字段
        params["access_token"] = access_token
        params["device_no"] = device_no
        params["product_name"] = miai_product_code

        # 修改 image_header 生成逻辑
        new_header = f"-{miai_product_code}-01-02-03-04-"
        params["image_header"] = new_header

        # 6. 写回文件
        try:
            with open(params_path, 'w', encoding='utf-8') as f:
                json.dump(params, f, indent=4, ensure_ascii=False)
            log(f"成功更新参数文件: {params_path}", LogType.INFO)
            return True
        except Exception as e:
            log(f"更新参数文件失败: {e}", LogType.ERROR)
            return False


# 图片加载缓存
@lru_cache(maxsize=1)
def load_image_bytes():
    """加载并缓存所有图片字节"""
    img_bytes = []
    img_path = get_relative_path('images')

    if not os.path.exists(img_path):
        log(f"图片目录不存在: {img_path}", LogType.WARNING)
        return img_bytes

    for root, _, files in os.walk(img_path):
        for file in files:
            if file.lower().endswith('.jpg'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'rb') as f:
                        img_bytes.append(f.read())
                except Exception as e:
                    log(f"加载图片失败: {file_path} - {str(e)}", LogType.ERROR)

    if not img_bytes:
        log("警告: 图片目录中没有找到任何.jpg文件", LogType.WARNING)

    return img_bytes


class BashGrpcMock:
    def __init__(self, channel, loops):
        self.counter_task = 2100
        self.counter_photo = 1
        self.loops = loops
        self.fixed_values = [1, 2, 3, 4, 5]
        self.index = 0
        self.stop_event = threading.Event()

        # 加载证书和配置
        certs = ResourceLoader.get_certs()
        self.result = ResourceLoader.get_params()  # 使用静态加载的参数

        # 创建gRPC通道
        creds = grpc.ssl_channel_credentials(**certs)
        self.stub = grpc_control.BashServiceStub(grpc.secure_channel(
            channel, creds,
            options=(('grpc.ssl_target_name_override', "svfactory.com.cn",),)
        ))

        # 加载图片
        self.img_bytes = load_image_bytes()
        self.i_r_images = max(len(self.img_bytes) - 1, 0)

    def run(self):
        """执行主循环逻辑"""
        loop_count = 0
        while not self.stop_event.is_set() and (self.loops <= 0 or loop_count < self.loops):
            self._process_single_request()
            loop_count += 1

    def stop(self):
        self.stop_event.set()

    # 处理单个请求(可修改光学面号等参数)
    def _process_single_request(self):
        """处理单个请求"""
        now_time = time.time() * 1000
        now_str = (time.strftime("%Y%m%d%H%M%S", time.localtime(now_time / 1000))
                   + f"{now_time % 1000:03.0f}")

        # 修改图片头生成逻辑
        device_no = self.result["device_no"]
        image_header = (
            f"{random_part1}-{random_part2}-{random_part3}-"
            f"{device_no}-01-02-03-04-{now_str}.jpg"
        )

        # 更新索引和计数器
        self.index = (self.index + 1) % len(self.fixed_values)
        if self.index == 0:
            self.counter_task += 1

        # 发送gRPC请求
        self.grpc_request(image_header)

        # log(f"生成的图片头: {image_header}", LogType.INFO)
        # log(f"请求设备号: {self.result['device_no']}", LogType.INFO)

    def _build_model_result(self, image_header):
        """构建模型结果数据结构"""
        return {
            "version": "1.0",
            "jsonVersion": "1.0",
            "flags": {},
            "imageWidth": 1400,
            "imageHeight": 1400,
            "imageDepth": 1,
            "imagePath": image_header,
            "finalRes": "",
            "deepRes": "NG",
            "cvRes": "NG",
            "bashRes": "NG",
            "dataRes": "NG",
            "bashUserId": "",
            "dataModelVersion": "10.7.7",
            "tryDataRes": "",
            "tryDataModelVersion": "4.3.2",
            "shapes": [
                # 示例形状数据1
                {
                    "if_model": True,
                    "model_id": "M1",
                    "label_type": "1",
                    "pre_label": "qipao",
                    "class_id": "",
                    "class_type": "NG",
                    "label": "qipao",
                    "score": 0.4303,
                    "shape_type": "rectangle",
                    "id": "1714032656556765",
                    "points": [[727.0714, 103.0], [1065.0714, 439.0]],
                    "point_arr": [[227.07, 284.54], [225.07, 283.34],
                                  [223.07, 283.34], [222.07, 285.14]],
                    "data_type": 1,
                    "data_result": "NG",
                    "try_data_result": "OK",
                    "data_rule_type": 2,
                    "data_filter_rule_id": 232,
                    "data_detection_rule_id": 123,
                    "data_rule_kindof": 1,
                    "depth_defect_code": "baidian",
                    "upload_cloud": 1,
                    "upload_cloud_rule_type": 1,
                    "upload_cloud_rule_id": 2323,
                    "defect_feature": {
                        "max_length": 252.976,
                        "smoothness": 0.0212465,
                        "angle": 0,
                        "curvature": 0.25,
                        "straight_line": 0,
                        "length_width_ratio": 0.239837,
                        "avg_height": 0,
                        "max_height": 0
                    }
                },
                # 示例形状数据2
                {
                    "if_model": True,
                    "model_id": "M1",
                    "label_type": "1",
                    "pre_label": "yise",
                    "class_id": "",
                    "class_type": "unconfirmed",
                    "label": "yise",
                    "score": 0.4303,
                    "shape_type": "rectangle",
                    "id": "1714032656556765",
                    "points": [[332.088888888888, 709.0], [490.0, 859.0]],
                    "point_arr": [[227.07, 284.54], [225.07, 283.34],
                                  [223.07, 283.34], [222.07, 285.14]],
                    "data_type": 1,
                    "data_result": "unconfirmed",
                    "try_data_result": "OK",
                    "data_rule_type": 2,
                    "data_filter_rule_id": 232,
                    "data_detection_rule_id": 123,
                    "data_rule_kindof": 1,
                    "depth_defect_code": "baidian",
                    "upload_cloud": 1,
                    "upload_cloud_rule_type": 1,
                    "upload_cloud_rule_id": 2323,
                    "defect_feature": {
                        "max_length": 252.976,
                        "smoothness": 0.0212465,
                        "angle": 0,
                        "curvature": 0.25,
                        "straight_line": 0,
                        "length_width_ratio": 0.239837,
                        "avg_height": 0,
                        "max_height": 0
                    }
                },
                # 示例形状数据3
                {
                    "if_model": True,
                    "model_id": "M1",
                    "label_type": "1",
                    "pre_label": "aotudian",
                    "class_id": "",
                    "class_type": "NG",
                    "label": "aotudian",
                    "score": 0.4303,
                    "shape_type": "polygon",
                    "id": "1714032656556765",
                    "points": [
                        [1046.83, 1119.07], [1108.83, 1199.07],
                        [1180.83, 1195.07], [1248.83, 1081.07],
                        [1226.83, 1027.07], [1142.83, 993.07],
                        [1102.83, 971.07], [1000.83, 963.07],
                        [952.83, 1001.07], [934.83, 1047.07],
                        [952.83, 1069.07], [990.83, 1103.07]
                    ],
                    "point_arr": [[227.07, 284.54], [225.07, 283.34],
                                  [223.07, 283.34], [222.07, 285.14]],
                    "data_type": 1,
                    "data_result": "OK",
                    "try_data_result": "OK",
                    "data_rule_type": 2,
                    "data_filter_rule_id": 232,
                    "data_detection_rule_id": 123,
                    "data_rule_kindof": 1,
                    "depth_defect_code": "baidian",
                    "upload_cloud": 1,
                    "upload_cloud_rule_type": 1,
                    "upload_cloud_rule_id": 2323,
                    "defect_feature": {
                        "max_length": 252.976,
                        "smoothness": 0.0212465,
                        "angle": 0,
                        "curvature": 0.25,
                        "straight_line": 0,
                        "length_width_ratio": 0.239837,
                        "avg_height": 0,
                        "max_height": 0
                    }
                }
            ]
        }

    def grpc_request(self, image_header: str):
        """发送gRPC请求并处理响应"""
        start_time = time.perf_counter()
        try:
            # 构建请求
            request = grpc_api.ImageRecheckRequest(
                access_token=self.result["access_token"],
                device_no=self.result["device_no"],
                product_name=self.result["product_name"],
                optical_side_id=self.result["optical_side_id"],
                width=self.result["width"],
                height=self.result["height"],
                encoded_image=random.choice(self.img_bytes) if self.img_bytes else b'',
                image_header=image_header,
                result=self.result["DetectionResult"],
                model_version=self.result["model_version"],
                request_type=self.result["request_type"],
                is_crop=Constants.IS_CROP,
                detection_area_type=Constants.DETECTION_AREA_TYPE,
                detection_area=[{"points": [{"x": 2, "y": 3}, {"x": 6, "y": 7},
                                            {"x": 7, "y": 1}, {"x": 4, "y": 9}]}],
                detection_comment="检测逻辑说明",
                proto_version="",
                system_type=Constants.SYSTEM_TYPE,
                expand_feature="{}",
                model_result=json.dumps(self._build_model_result(image_header))
            )

            # 发送请求
            response = self.stub.ImageRecheck(request)

            # 处理响应
            cost_time = time.perf_counter() - start_time
            res = json.dumps(MessageToDict(response), ensure_ascii=False)

        except grpc.RpcError as e:
            cost_time = time.perf_counter() - start_time
            res = {"imageRecheckResult": "gRPC Error", "details": f"{e.code()}: {e.details()}"}
            log(f"gRPC错误: {e.code()} {e.details()}", LogType.ERROR)

        except Exception as e:
            cost_time = time.perf_counter() - start_time
            res = {"imageRecheckResult": "Exception", "details": f"{str(e)}"}
            log(f"未处理异常: {traceback.format_exc()}", LogType.CRITICAL)

        # 记录日志
        log(
            f'函数 {self.grpc_request.__name__} 耗时: {cost_time:.6f}s, '
            f'图片头: {image_header}, 响应: {res}',
            LogType.LOGIC,
            is_split=False
        )


# 手动推图
def push_images_manual(config_data=None):
    """手动输入模式测试"""
    print("测试开始 (手动模式)")
    config = ResourceLoader.get_config(config_data)

    # === 新增：在启动前更新JSON文件 ===
    update_result = ResourceLoader.update_params_json()
    if not update_result:
        print("警告：参数文件更新失败，使用现有配置继续执行")

    print("性能Bash工具 - 手动模式")
    for i, url in enumerate(config['channel'], 1):
        print(f"{i}. {url}")

    address_no = int(input("请输入GRPC请求编号: "))
    i_threads = int(input("请输入线程数: "))
    i_loops = int(input("请输入循环数: "))

    run_test(config, address_no, i_threads, i_loops)


# 自动推图
def push_images_auto(config_data=None):
    """自动执行模式测试"""
    print("测试开始 (自动模式)")
    config = ResourceLoader.get_config(config_data)

    # === 新增：在启动前更新JSON文件 ===
    update_result = ResourceLoader.update_params_json()
    if not update_result:
        print("警告：参数文件更新失败，使用现有配置继续执行")

    # 使用默认参数
    address_no = Constants.DEFAULT_ADDRESS_NO
    i_threads = Constants.DEFAULT_THREADS
    i_loops = Constants.DEFAULT_LOOPS

    print(f"自动模式参数: GRPC请求编号={address_no}, 线程数={i_threads}, 循环数={i_loops}")

    # 创建推图实例
    grpc_mock = BashGrpcMock(config['channel'][address_no - 1], i_loops)

    # 启动推图线程
    push_thread = threading.Thread(target=grpc_mock.run)
    push_thread.start()

    # 返回推图实例以便控制
    return grpc_mock


def run_test(config, address_no, i_threads, i_loops):
    """执行测试的通用方法"""
    log("开始测试", LogType.LOGIC)

    # 使用线程池管理并发
    with ThreadPoolExecutor(max_workers=i_threads) as executor:
        futures = [
            executor.submit(BashGrpcMock(config['channel'][address_no - 1], i_loops).run)
            for _ in range(i_threads)
        ]

        # 等待所有任务完成
        for future in futures:
            try:
                future.result()
            except Exception as e:
                log(f"线程执行异常: {str(e)}", LogType.ERROR)

    log("测试完成", LogType.LOGIC)
