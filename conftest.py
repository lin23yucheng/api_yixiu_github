"""全局pytest插件注册。"""

# 让任意目录下的pytest执行都自动启用质量度量采集。
pytest_plugins = ["AI_testing_framework.quality_metrics"]

