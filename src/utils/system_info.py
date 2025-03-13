import socket
import uuid


def get_mac_address():
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]

    return ":".join([mac[i:i + 2] for i in range(0, 12, 2)])

def generate_uuid() -> str:
    """
    生成 UUID v4
    """
    # 方法1：使用 Python 的 uuid 模块
    return str(uuid.uuid4())

def get_local_ip():
    try:
        # 创建一个临时 socket 连接来获取本机 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'