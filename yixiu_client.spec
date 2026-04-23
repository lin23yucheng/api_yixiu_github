# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\client_gui.py'],
    pathex=['C:\\Users\\admin\\PycharmProjects\\yixiu_api_process'],
    binaries=[],
    datas=[('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\config', 'config'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\testcase', 'testcase'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\bash', 'bash'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\common', 'common'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\api', 'api'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\utils', 'utils'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\testdata', 'testdata'), ('C:\\Users\\admin\\PycharmProjects\\yixiu_api_process\\test_run.py', '.')],
    hiddenimports=[
        # 核心框架和插件
        'test_run', 'allure_pytest', 'allure_python_commons', 'random_order',
        'allure_pytest.plugin', 'random_order.plugin',
        'pytest', 'pytest_html', 'pytest_order', 'pytest_xdist',

        # HTTP 和网络
        'requests', 'urllib3', 'charset_normalizer', 'idna', 'certifi',
        'websocket', 'websocket_client',
        'grpcio', 'grpcio_tools', 'protobuf', 'google',
        'PySocks', 'h11', 'outcome', 'sniffio', 'sortedcontainers',
        'trio', 'trio_websocket', 'wsproto',

        # Web 自动化 - selenium 主模块和子模块
        'selenium', 'selenium.webdriver', 'selenium.webdriver.chrome',
        'selenium.webdriver.firefox', 'selenium.webdriver.edge',
        'selenium.webdriver.common.action_chains',
        'selenium.webdriver.common.alert', 'selenium.webdriver.common.by',
        'selenium.webdriver.common.keys', 'selenium.webdriver.common.window',
        'selenium.webdriver.support', 'selenium.webdriver.support.ui',
        'selenium.webdriver.support.expected_conditions',
        'webdriver_manager', 'webdriver_manager.chrome', 'webdriver_manager.firefox',
        'webdriver_manager.microsoft', 'webdriver_manager.core',

        # 数据处理和解析
        'lxml', 'beautifulsoup4', 'xlrd', 'openpyxl',
        'jsonschema', 'jsonschema_specifications', 'referencing', 'rpds',

        # 系统和工具
        'psutil', 'psycopg2', 'dotenv', 'yaml',
        'atomicwrites', 'attrs', 'pluggy', 'six',
        'more_itertools', 'namedlist', 'colorama', 'packaging',
        'dateutil', 'utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='yixiu_client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='yixiu_client',
)
