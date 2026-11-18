# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


# PyInstaller 执行 spec 时不会注入 __file__，应使用 SPECPATH/SPEC。
SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parent


a = Analysis(
    [str(PROJECT_ROOT / 'client' / 'client_gui.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / 'AI'), 'AI'),
        (str(PROJECT_ROOT / 'config'), 'config'),
        (str(PROJECT_ROOT / 'testcase'), 'testcase'),
        (str(PROJECT_ROOT / 'bash'), 'bash'),
        (str(PROJECT_ROOT / 'common'), 'common'),
        (str(PROJECT_ROOT / 'api'), 'api'),
        (str(PROJECT_ROOT / 'utils'), 'utils'),
        (str(PROJECT_ROOT / 'testdata'), 'testdata'),
        (str(PROJECT_ROOT / 'client' / 'test_run.py'), 'client'),
    ],
    hiddenimports=[
        'AI', 'AI.ai_analyzer', 'AI.semantic_assertion_engine', 'AI.run_semantic_assertion',
        # 核心框架和插件
        'client.test_run', 'allure_pytest', 'allure_python_commons', 'random_order',
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
        'selenium.webdriver.chrome.options', 'selenium.webdriver.chrome.service',
        'selenium.webdriver.chrome.webdriver',
        'selenium.webdriver.firefox.options', 'selenium.webdriver.firefox.service',
        'selenium.webdriver.edge.options', 'selenium.webdriver.edge.service',
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

