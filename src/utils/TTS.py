import pyttsx3
import threading
import logging
import io
import wave
import numpy as np
import tempfile
import os

logger = logging.getLogger(__name__)

class TextToSpeech:
    """文本转语音模块 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """确保单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化TTS引擎"""
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        try:
            self.engine = pyttsx3.init()
            # 设置默认语速和音量
            self.engine.setProperty('rate', 180)  # 设置语速
            self.engine.setProperty('volume', 1.0)  # 设置音量，范围为 0.0-1.0
            logger.info("TTS引擎初始化成功")
        except Exception as e:
            logger.error(f"TTS引擎初始化失败: {e}")
            self.engine = None
    
    @classmethod
    def get_instance(cls):
        """获取TTS实例（线程安全）"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance
    
    def set_rate(self, rate):
        """设置语音速率"""
        if self.engine:
            self.engine.setProperty('rate', rate)
    
    def set_volume(self, volume):
        """设置音量"""
        if self.engine:
            self.engine.setProperty('volume', volume)
    
    def speak_text(self, text):
        """播放文本语音（阻塞）"""
        if not self.engine:
            logger.error("TTS引擎未初始化")
            return False
            
        try:
            self.engine.say(text)
            self.engine.runAndWait()
            return True
        except Exception as e:
            logger.error(f"语音播放失败: {e}")
            return False
    
    def text_to_wav(self, text, sample_rate=16000):
        """
        将文本转换为WAV音频数据
        
        Args:
            text: 要转换的文本
            sample_rate: 采样率
            
        Returns:
            音频数据的字节序列，如果失败则返回None
        """
        if not self.engine:
            logger.error("TTS引擎未初始化")
            return None
            
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # 保存语音到临时文件
            self.engine.save_to_file(text, temp_path)
            self.engine.runAndWait()
            
            # 读取文件数据
            with open(temp_path, 'rb') as f:
                wav_data = f.read()
                
            # 删除临时文件
            os.unlink(temp_path)
            
            # 如果需要转换采样率，可以在这里处理
            # 这里简单地返回原始数据
            return wav_data
            
        except Exception as e:
            logger.error(f"文本转WAV失败: {e}")
            return None
            
    def text_to_pcm(self, text, sample_rate=16000, channels=1):
        """
        将文本转换为PCM格式的音频数据
        
        Args:
            text: 要转换的文本
            sample_rate: 采样率
            channels: 声道数
            
        Returns:
            PCM格式的音频数据字节序列，如果失败则返回None
        """
        wav_data = self.text_to_wav(text, sample_rate)
        if not wav_data:
            return None
            
        try:
            # 使用wave模块解析WAV数据
            with wave.open(io.BytesIO(wav_data), 'rb') as wav_file:
                # 提取PCM数据
                pcm_data = wav_file.readframes(wav_file.getnframes())
                return pcm_data
        except Exception as e:
            logger.error(f"WAV转PCM失败: {e}")
            return None 