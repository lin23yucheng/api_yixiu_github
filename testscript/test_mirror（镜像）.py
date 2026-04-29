"""
自动贴镜像
"""
import allure
from common import Assert
from api.api_space import ApiSpace
assertions = Assert.Assertions()

# 镜像配置 - 将需要更新的镜像路径填入对应位置，不需要更新的留空
IMAGE_CONFIG = {
    1: "",  # yolo训练
    2: "",  # yolo模型格式转换
    3: "",  # yolo测试
    4: "mtl-sidecar-image:20260421132455-296-fat",  # 边端监控sidecar-image
    5: "",  # 切图
    6: "",  # 训练
    7: "",  # triton推理
    8: "",  # mtlGateway
    9: "",  # 过滤非检测区
    10: "",  # trivision推理
    11: "",  # cv
    12: ""   # yolo12训练
}

# 固定的镜像仓库前缀
IMAGE_REGISTRY_PREFIX = "hub.svfactory.com.cn:6443/ty/"


@allure.feature("场景：自动贴镜像")
class TestMirror:
    @classmethod
    def setup_class(cls):
        cls.api_space = ApiSpace()

    @allure.story("自动更新镜像")
    def test_update_images(self):
        """
        自动更新配置的镜像
        只更新IMAGE_CONFIG中非空的镜像
        """
        updated_count = 0

        for image_type, image_suffix in IMAGE_CONFIG.items():
            if image_suffix:  # 只处理非空的镜像路径
                # 自动添加固定前缀
                image_path = IMAGE_REGISTRY_PREFIX + image_suffix
                try:
                    # 根据image_type获取对应的描述
                    type_descriptions = {
                        1: "yolo训练",
                        2: "yolo模型格式转换",
                        3: "yolo测试",
                        4: "边端监控",
                        5: "切图",
                        6: "训练",
                        7: "triton推理",
                        8: "mtlGateway",
                        9: "过滤非检测区",
                        10: "trivision推理",
                        11: "cv",
                        12: "yolo12训练"
                    }

                    image_desc = type_descriptions.get(image_type, f"未知类型({image_type})")

                    with allure.step(f"更新{image_desc}镜像 (类型: {image_type})"):
                        # 调用api_space.py中的add_image方法
                        response = self.api_space.add_image(image_type, image_path)

                        # 解析响应
                        response_data = response.json()
                        if response_data.get("success"):
                            allure.attach(
                                f"镜像类型: {image_type}\n镜像路径: {image_path}\n响应: {response_data}",
                                name=f"成功更新{image_desc}",
                                attachment_type=allure.attachment_type.TEXT
                            )
                            print(f"成功更新{image_desc}镜像，类型: {image_type}，路径: {image_path}")
                            updated_count += 1
                        else:
                            error_msg = response_data.get("msg", "未知错误")
                            allure.attach(
                                f"镜像类型: {image_type}\n镜像路径: {image_path}\n错误: {error_msg}",
                                name=f"更新{image_desc}失败",
                                attachment_type=allure.attachment_type.TEXT
                            )
                            print(f"更新{image_desc}镜像失败，类型: {image_type}，错误: {error_msg}")

                except Exception as e:
                    print(f"更新镜像类型 {image_type} 时发生异常: {str(e)}")
                    allure.attach(
                        str(e),
                        name=f"镜像类型{image_type}异常",
                        attachment_type=allure.attachment_type.TEXT
                    )

        print(f"镜像更新完成，共更新了 {updated_count} 个镜像")
        allure.attach(
            f"总共更新了 {updated_count} 个镜像",
            name="更新统计",
            attachment_type=allure.attachment_type.TEXT
        )


if __name__ == "__main__":
    test_instance = TestMirror()
    test_instance.setup_class()
    test_instance.test_update_images()
