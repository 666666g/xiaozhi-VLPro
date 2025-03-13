import cv2
import base64
import logging
import threading
import time
import requests
import json
from io import BytesIO
from PIL import Image

logger = logging.getLogger("VisionProcessor")

class VisionProcessor:
    """视觉处理器，用于捕获摄像头画面并调用GLM-4V-Flash API进行图像理解"""
    
    def __init__(self, camera_id=0, api_key=None):
        """初始化视觉处理器
        
        Args:
            camera_id: 摄像头ID，默认为0
            api_key: GLM-4V-Flash API密钥
        """
        self.camera_id = camera_id
        self.api_key = api_key
        self.cap = None
        self.running = False
        self.thread = None
        self.frame = None
        self.last_process_time = 0
        self.process_interval = 5  # 默认5秒处理一次图像
        self.last_vision_result = ""
        self.on_vision_result = None
        
        # 修正 API 配置 - 使用智谱AI的API地址
        self.api_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        logger.info(f"视觉处理器初始化，摄像头ID: {camera_id}")
    
    def start(self):
        """启动视觉处理"""
        if self.running:
            logger.warning("视觉处理器已经在运行")
            return False
            
        try:
            logger.info(f"尝试打开摄像头 {self.camera_id}")
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                logger.error(f"无法打开摄像头 {self.camera_id}，请检查摄像头连接或权限")
                return False
                
            # 尝试读取一帧，确认摄像头工作正常
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.error("摄像头无法读取图像帧，请检查摄像头是否被其他程序占用")
                return False
            else:
                logger.info(f"成功读取图像帧，尺寸: {frame.shape}")
                
            self.running = True
            # 将守护线程改为非守护线程，确保主线程退出时视觉处理线程不会自动终止
            self.thread = threading.Thread(target=self._process_loop, daemon=False)
            self.thread.start()
            logger.info("视觉处理器线程已启动")
            return True
        except Exception as e:
            logger.error(f"启动视觉处理器失败: {e}", exc_info=True)
            return False
    
    def stop(self):
        """停止视觉处理"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
        logger.info("视觉处理器已停止")
    
    def _process_loop(self):
        """视觉处理循环"""
        logger.info("视觉处理循环开始运行")
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning("无法读取摄像头画面")
                    time.sleep(1)
                    continue
                    
                # 只更新当前帧，不自动处理图像
                self.frame = frame
                
                # 移除自动处理图像的代码
                # current_time = time.time()
                # if current_time - self.last_process_time >= self.process_interval:
                #     self.last_process_time = current_time
                #     logger.debug("启动图像处理线程")
                #     threading.Thread(target=self._process_image, args=(frame.copy(),)).start()
                    
                time.sleep(0.03)  # 约30fps
            except Exception as e:
                logger.error(f"视觉处理循环错误: {e}", exc_info=True)
                time.sleep(1)
        logger.info("视觉处理循环已结束")
    
    def _process_image(self, frame):
        """处理图像并调用GLM-4V-Flash API
        
        Args:
            frame: 要处理的图像帧
            
        Returns:
            str: 成功时返回识别结果，失败时返回空字符串
        """
        try:
            # 将OpenCV的BGR格式转换为RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            
            # 调整图像大小以减小API请求大小
            max_size = 800
            width, height = pil_image.size
            if width > max_size or height > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                pil_image = pil_image.resize((new_width, new_height))
            
            # 将图像转换为Base64编码
            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG", quality=80)
            img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # 修正 API 请求格式，按照官方文档构建
            payload = {
                "model": "glm-4v-flash",  # 使用免费的模型
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": "请简洁描述这张图片中的内容，重点关注主要物体和场景。"
                            },
                            {
                                "type": "image_url", 
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_str}"
                                }
                            }
                        ]
                    }
                ],
                "stream": False
            }
            
            # 发送API请求
            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                # 修正结果解析方式，按照官方文档的响应格式
                vision_text = result["choices"][0]["message"]["content"]
                self.last_vision_result = vision_text
                logger.info(f"视觉识别结果: {vision_text[:100]}...")
                
                # 调用回调函数
                if self.on_vision_result:
                    self.on_vision_result(vision_text)
                    
                return vision_text
            else:
                logger.error(f"API请求失败: {response.status_code}, {response.text}")
                return ""
                
        except Exception as e:
            logger.error(f"处理图像失败: {e}")
            return ""
    
    def get_current_frame(self):
        """获取当前帧"""
        return self.frame
    
    def get_last_result(self):
        """获取最近的视觉识别结果"""
        return self.last_vision_result
    
    def set_api_key(self, api_key):
        """设置API密钥"""
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def set_process_interval(self, seconds):
        """设置处理间隔"""
        self.process_interval = max(1, seconds)  # 至少1秒 