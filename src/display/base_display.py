from abc import ABC, abstractmethod
from typing import Optional, Callable

class BaseDisplay(ABC):
    """显示接口的抽象基类"""
    
    @abstractmethod
    def set_callbacks(self,
                     press_callback: Optional[Callable] = None,
                     release_callback: Optional[Callable] = None,
                     status_callback: Optional[Callable] = None,
                     text_callback: Optional[Callable] = None,
                     emotion_callback: Optional[Callable] = None):
        """设置回调函数"""
        pass

    @abstractmethod
    def update_button_status(self, text: str):
        """更新按钮状态"""
        pass

    @abstractmethod
    def update_status(self, status: str):
        """更新状态文本"""
        pass

    @abstractmethod
    def update_text(self, text: str):
        """更新TTS文本"""
        pass

    @abstractmethod
    def update_emotion(self, emotion: str):
        """更新表情"""
        pass

    @abstractmethod
    def update_volume(self, volume: int):
        """更新系统音量"""
        pass

    @abstractmethod
    def start(self):
        """启动显示"""
        pass

    @abstractmethod
    def on_close(self):
        """关闭显示"""
        pass

    @abstractmethod
    def update_connection_status(self, connected: bool):
        """更新连接状态"""
        pass