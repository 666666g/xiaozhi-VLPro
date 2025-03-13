import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("VisionConfig")

class VisionConfig:
    """视觉功能配置管理"""
    
    CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
    VISION_CONFIG_FILE = CONFIG_DIR / "vision_config.json"
    
    DEFAULT_CONFIG = {
        "enabled": False,
        "camera_id": 0,
        "api_key": "",
        "process_interval": 5,
        "auto_capture": False  # 确保默认禁用自动捕获
    }
    
    @classmethod
    def load_config(cls):
        """加载视觉配置"""
        try:
            # 确保配置目录存在
            if not cls.CONFIG_DIR.exists():
                cls.CONFIG_DIR.mkdir(parents=True)
                logger.info(f"创建配置目录: {cls.CONFIG_DIR}")
            
            # 如果配置文件不存在，创建默认配置
            if not cls.VISION_CONFIG_FILE.exists():
                # 修改默认配置，启用视觉功能
                default_config = cls.DEFAULT_CONFIG.copy()
                default_config["enabled"] = True
                
                with open(cls.VISION_CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                logger.info(f"已创建默认视觉配置文件: {cls.VISION_CONFIG_FILE}")
                return default_config
            
            # 读取配置文件
            with open(cls.VISION_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 确保所有必要的配置项都存在
            for key, value in cls.DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            
            return config
        except Exception as e:
            logger.error(f"加载视觉配置失败: {e}", exc_info=True)
            # 出错时返回默认配置并启用
            default_config = cls.DEFAULT_CONFIG.copy()
            default_config["enabled"] = True
            return default_config
    
    @classmethod
    def save_config(cls, config):
        """保存视觉配置"""
        try:
            with open(cls.VISION_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            logger.info("视觉配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存视觉配置失败: {e}")
            return False
    
    @classmethod
    def update_config(cls, key, value):
        """更新特定配置项"""
        config = cls.load_config()
        if key in config:
            config[key] = value
            return cls.save_config(config)
        return False 