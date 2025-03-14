import os
import base64
import json
import requests
import threading
import logging

logger = logging.getLogger(__name__)

class ImageAnalyzer:
    _instance = None
    _lock = threading.Lock()
    client = None
    
    def __new__(cls):
        """确保单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def init(self, api_key, model="glm-4v-flash", base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions"):
        """初始化图像分析器
        
        Args:
            api_key: 智谱 API 密钥
            model: 模型名称，可选 "glm-4v-flash"(免费), "glm-4v", "glm-4v-plus", "glm-4v-plus-0111"
            base_url: API 基础 URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    @classmethod
    def get_instance(cls):
        """获取图像分析器实例（线程安全）"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance
    
    def analyze_image(self, base64_image, prompt="图中描绘的是什么景象,请详细描述，因为用户可能是盲人") -> str:
        """分析图片并返回结果
        
        Args:
            base64_image: Base64 编码的图像
            prompt: 提示文本
            
        Returns:
            str: 分析结果
        """
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "stream": True
        }
        
        try:
            logger.info(f"发送请求到: {self.base_url}")
            logger.info(f"使用模型: {self.model}")
            response = requests.post(self.base_url, headers=self.headers, json=payload, stream=True)
            response.raise_for_status()
            
            message = ""
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]  # 去掉 "data: " 前缀
                        if data == "[DONE]":
                            break
                        
                        try:
                            json_data = json.loads(data)
                            if "choices" in json_data and json_data["choices"]:
                                content = json_data["choices"][0].get("delta", {}).get("content", "")
                                if content:
                                    logger.info(content)
                                    message += content
                        except json.JSONDecodeError:
                            pass
            
            return message
        except Exception as e:
            logger.error(f"分析图像时出错: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应状态码: {e.response.status_code}")
                logger.error(f"响应内容: {e.response.text}")
            return f"分析图像时出错: {e}" 