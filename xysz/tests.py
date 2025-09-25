import requests
import json
import websocket
from datetime import datetime


def upload_coin_reminder(coin_platform, coin_name, reminder_name, side, price, timetype):

    url = "http://8.216.32.13:8080/coin/uploadCoinReminder"
    
    # 构造请求参数
    params = {
        "coinPlatform": coin_platform,
        "coinName": coin_name,
        "reminderName": reminder_name,
        "side": side,
        "price": str(price),
        "timetype": timetype
    }
    
    try:
        # 发送GET请求
        response = requests.get(url, params=params)
        
        # 检查响应状态码
        if response.status_code == 200:
            return response.json()  # 假设返回的是JSON格式
        else:
            return {"code": -1, "msg": f"请求失败，状态码: {response.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"code": -1, "msg": f"请求异常: {str(e)}"}
    
    

def send_trading_signal(
        type_value: str, 
        coin: str, 
        coinPlatform: str, 
        time_frame: int, 
        plan_name: str, 
        side: str, 
        selltype: str,
        price: float,
        time2: str,  # 格式如 "14:55"
        ws_url: str = "ws://8.216.32.13:8802"
    ):

    # 验证时间周期
    valid_timeframes = [60, 300, 900, 3600]
    if time_frame not in valid_timeframes:
        raise ValueError(f"无效time值，必须是{valid_timeframes}之一")
    
    # 验证交易方向
    valid_sides = ["OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT"]
    if side not in valid_sides:
        raise ValueError(f"无效side值，必须是{valid_sides}之一")
    
    # 构建JSON数据
    signal = {
        "code": 1,  # 固定值
        "type": type_value,
        "coin": coin.upper(),
        "coinPlatform":coinPlatform,
        "time": time_frame,
        "plan": plan_name,
        "role": 101,  # 固定值
        "side": side,
        "selltype": selltype,
        "price": price,
        "time2": time2
    }
    
    # 转换为JSON字符串
    json_data = json.dumps(signal)
    
    try:
        # 创建WebSocket连接
        ws = websocket.create_connection(ws_url)
        
        # 发送信号
        ws.send(json_data)
        print(f"{plan_name}_{coinPlatform}_{coin}信号已发送: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        # print(f"发送内容: {json_data}")
        
        # 关闭连接
        ws.close()
        return True
        
    except Exception as e:
        print(f"发送失败: {str(e)}")
        return False


def send_stock_alert(coin: str, time: int, plan: str, msg: str):
    """
    同步方式发送股票警报消息到WebSocket服务器
    
    参数:
        coin: 币种 (BTC, ETH, SOL, DOGE, XRP)
        time: 时间间隔 (60, 300, 900, 3600) 秒
        plan: 策略名称 (例如: grid_fly, 谐波模式)
        msg: 消息内容 (格式: "多/空 HH:mm,价格" 例如: "多 14:55,2433.96")
    """
    # 验证输入参数
    valid_coins = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
    valid_times = [60, 300, 900, 3600]
    
    if coin not in valid_coins:
        raise ValueError(f"无效的coin参数，必须是: {valid_coins}")
    if time not in valid_times:
        raise ValueError(f"无效的time参数，必须是: {valid_times}")
    
    # 构造消息JSON
    message = {
        "code": 1,
        "type": "stockalert",
        "coin": coin,
        "time": time,
        "plan": plan,
        "role": 101,
        "msg": msg
    }
    
    # WebSocket服务器地址
    ws_url = "ws://39.108.117.80:8802"
    
    try:
        ws = websocket.WebSocket()
        ws.connect(ws_url)
        ws.send(json.dumps(message))
        print(f"已发送消息: {message}")
        ws.close()  # 关闭连接
    except Exception as e:
        print(f"发送消息时出错: {e}")
        if 'ws' in locals():
            ws.close()  # 确保连接关闭


# 震荡区分
def send_mode_signal(
        coin: str, 
        coinPlatform: str, 
        side: int, 
        plan: str,
        time: int, 
        mode: int, 
        multiple: str,
        multiple2: str,
        dpo: float = 0.0,
        tp: float = 0.0,
        sl: float = 0.0,
        ws_urls: list = ["ws://8.216.32.13:8802", "ws://47.84.194.2:8802"]
    ):
    """
    发送交易模式设置信号到WebSocket服务器
    
    参数:
    coin: 交易币种 (BTC, ETH, SOL, DOGE, XRP)
    side: 交易方向 (1:多, 2:空)
    mode: 市场模式 (1:震荡, 2:趋势)
    dpo: 网格百分比 (仅mode=1时有效)
    ws_url: WebSocket服务器地址
    """
    # 验证参数
    if side not in (1, 2):
        raise ValueError("side必须是1(多)或2(空)")
    if mode not in (1, 2):
        raise ValueError("mode必须是1(震荡)或2(趋势)")

    # 构建JSON数据
    signal = {
        "code": 1,      # 固定值
        "type": "setMode",  # 固定值
        "coinPlatform": coinPlatform,
        "coin": coin.upper(),
        "plan": plan,
        "time": time, 
        "role": 101,
        "side": side,
        "mode": mode,
        "dpo": dpo,
        "tp": tp,
        "sl": sl,
        "multiple": multiple,
        "multiple2": multiple2
    }
    
    # 转换为JSON字符串
    json_data = json.dumps(signal)
    
    results = []
    for ws_url in ws_urls:
        try:
            # 创建WebSocket连接
            ws = websocket.create_connection(ws_url)
            
            # 发送信号
            ws.send(json_data)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] KC模式信号已发送到{coinPlatform}_{coin}_{ws_url}")
            # print(f"发送内容: {json_data}")
            
            # 关闭连接
            ws.close()
            results.append(True)
            
        except Exception as e:
            print(f"发送到 {ws_url} 失败: {str(e)}")
            results.append(False)
    
    return all(results)
    

def send_fbmode_signal(
        coin: str, 
        side: int, 
        plan: str,
        mode: int, 
        dpo: float = 0.0,
        tp: float = 0.0,
        sl: float = 0.0,
        ws_url: str = "ws://8.216.32.13:8802"
    ):
    """
    发送交易模式设置信号到WebSocket服务器
    
    参数:
    coin: 交易币种 (BTC, ETH, SOL, DOGE, XRP)
    side: 交易方向 (1:多, 2:空)
    mode: 市场模式 (1:震荡, 2:趋势)
    dpo: 网格百分比 (仅mode=1时有效)
    ws_url: WebSocket服务器地址
    """
    # 验证参数
    if side not in (1, 2):
        raise ValueError("side必须是1(多)或2(空)")
    if mode not in (1, 2):
        raise ValueError("mode必须是1(震荡)或2(趋势)")

    # 构建JSON数据
    signal = {
        "code": 1,      # 固定值
        "type": "setMode",  # 固定值
        "coin": coin.upper(),
        "plan": plan,
        "role": 101,
        "side": side,
        "mode": mode,
        "dpo": dpo,
        "tp": tp,
        "sl":sl
    }
    
    # 转换为JSON字符串
    json_data = json.dumps(signal)
    
    try:
        # 创建WebSocket连接
        ws = websocket.create_connection(ws_url)
        
        # 发送信号
        ws.send(json_data)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{plan}_{coin}模式信号已发送")
        # print(f"发送内容: {json_data}")
        
        # 关闭连接
        ws.close()
        return True
        
    except Exception as e:
        print(f"发送失败: {str(e)}")
        return False
    


def send_KRmode_signal(
        coinPlatform: str,
        coin: str,
        time_frame: int, 
        plan: str, 
        side: str, 
        price: float,
        time2: str,
        ws_url: str = "ws://8.216.32.13:8802"
    ):

    # 构建JSON数据
    signal = {
            "code": 1,
            "type": "buysell",
            "coinPlatform": coinPlatform,
            "coin": coin,
            "time": str(time_frame),
            "plan": plan,
            "role": 101,
            "side": side,
            "price": str(price),
            "time2": time2
        }
    
    # 转换为JSON字符串
    json_data = json.dumps(signal)
    
    try:
        # 创建WebSocket连接
        ws = websocket.create_connection(ws_url)
        
        # 发送信号
        ws.send(json_data)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {plan}_{coinPlatform}_{coin}策略模式信号已发送")
        # print(f"发送内容: {json_data}")
        
        # 关闭连接
        ws.close()
        return True
        
    except Exception as e:
        print(f"发送失败: {str(e)}")
        return False