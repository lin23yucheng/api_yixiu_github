import zipfile
from PIL import Image


# 输出zip包中当前格式后缀与实际不一致的图片名称
def get_inconsistent_image_formats(zip_file_path):
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        file_names = zip_ref.namelist()
        for file_name in file_names:
            if file_name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                with zip_ref.open(file_name) as file:
                    try:
                        image = Image.open(file)
                        actual_format = image.format.lower()  # 将获取到的格式转换为小写，方便比较
                        expected_extension = file_name.split('.')[-1].lower()  # 获取文件名的后缀并转换为小写
                        if (actual_format == 'jpg' and expected_extension == 'jpeg') or (
                                actual_format == 'jpeg' and expected_extension == 'jpg'):
                            continue  # 如果是 jpg 和 jpeg 的互换，不做处理
                        elif actual_format != expected_extension:
                            print(f"图片 {file_name} 的实际格式与后缀不一致，实际格式: {actual_format}")
                    except Exception as e:
                        print(f"无法识别 {file_name} 的格式，错误信息: {e}")


# 调用示例
zip_file_path = r'C:\Users\admin\Desktop\项目文件\一休云\上传使用\上传数据集\生产-WOXINOCT\测试集-28ng.zip'
get_inconsistent_image_formats(zip_file_path)
