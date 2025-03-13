import requests
import json
import logging

from src.utils.config_manager import ConfigManager
from src.utils.system_info import get_local_ip

# 获取配置管理器实例
config = ConfigManager.get_instance()

# 配置日志
logger = logging.getLogger("Ota")


def get_ota_version():
    """获取 OTA 服务器的 MQTT 信息

    1. 发送设备信息到 OTA 服务器
    2. 获取最新的 MQTT 连接配置
    3. 更新 `mqtt_info` 变量

    Raises:
        ValueError: 当 MQTT 信息缺失或服务器返回无效数据时抛出
        requests.RequestException: 当网络请求失败时抛出
    """
    MAC_ADDR = config.get_device_id()
    OTA_VERSION_URL = config.get_config("NETWORK.OTA_VERSION_URL")


    headers = {
        "Device-Id": MAC_ADDR,
        "Content-Type": "application/json"
    }

    # 构建设备信息 payload
    payload = {
        "flash_size": 16777216,  # 闪存大小 (16MB)
        "minimum_free_heap_size": 8318916,  # 最小可用堆内存
        "mac_address": MAC_ADDR,  # 设备 MAC 地址
        "chip_model_name": "esp32s3",  # 芯片型号
        "chip_info": {
            "model": 9,
            "cores": 2,
            "revision": 2,
            "features": 18
        },
        "application": {
            "name": "xiaozhi",
        },
        "partition_table": [],  # 省略分区表信息
        "ota": {
            "label": "factory"
        },
        "board": {
            "type": "bread-compact-wifi",
            "ip": get_local_ip(),
            "mac": MAC_ADDR
        }
    }

    try:
        # 发送请求到 OTA 服务器
        response = requests.post(
            OTA_VERSION_URL,
            headers=headers,
            json=payload,
            timeout=10,  # 设置超时时间，防止请求卡死
            proxies={'http': None, 'https': None}  # 禁用代理
        )

        # 检查 HTTP 状态码
        if response.status_code != 200:
            logging.error(f"OTA 服务器错误: HTTP {response.status_code}")
            raise ValueError(f"OTA 服务器返回错误状态码: {response.status_code}")

        # 解析 JSON 数据
        response_data = response.json()

        # 调试信息：打印完整的 OTA 响应
        logging.debug(f"OTA 服务器返回数据: {json.dumps(response_data, indent=4, ensure_ascii=False)}")

        # 确保 "mqtt" 信息存在
        if "mqtt" in response_data:
            logging.info(f"MQTT 服务器信息已更新: {json.dumps(response_data, indent=4)}")
            return response_data["mqtt"]
        else:
            logging.error("OTA 服务器返回的数据无效: MQTT 信息缺失")
            raise ValueError("OTA 服务器返回的数据无效，请检查服务器状态或 MAC 地址！")

    except requests.Timeout:
        logging.error("OTA 请求超时，请检查网络或服务器状态")
        raise ValueError("OTA 请求超时！请稍后重试。")

    except requests.RequestException as e:
        logging.error(f"OTA 请求失败: {e}")
        raise ValueError("无法连接到 OTA 服务器，请检查网络连接！")
