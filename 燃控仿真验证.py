# -*- coding: utf-8 -*-
"""
低氮燃烧控制器主控板 —— 无硬件逻辑/换算仿真脚本（0 成本验证）
覆盖：4-20mA 采集换算与断线判断、热电偶温度换算(线性近似)、
      Modbus-RTU CRC16、CAN 帧模拟、燃烧联锁状态机。
运行：python 燃控仿真验证.py
不依赖任何开发板；结果打印到控制台，作为作品集仿真记录。
"""

# ---------- 1. 4-20mA 采集换算 ----------
ADC_FULL = 4095          # 12bit ADC
ADC_VREF = 3.3
SAMPLE_R = 250.0         # 采样电阻 250Ω：4-20mA -> 1~5V
DIVIDER = 5.0 / 3.3      # 5V 满幅经分压网络降到 ADC 3.3V 量程

def adc_to_current(adc_code):
    """ADC 码值 -> 4-20mA 电流；返回 (电流mA, 状态)
    链路: I*R=1~5V -> 分压 -> ADC；先还原采样电阻上电压再算电流。"""
    v_adc = adc_code / ADC_FULL * ADC_VREF
    v_sensor = v_adc * DIVIDER          # 还原 250Ω 上电压
    current_ma = v_sensor / SAMPLE_R * 1000.0
    if current_ma < 3.6:
        state = "FAULT_OPEN"   # 低于下限：断线/故障
    elif current_ma > 21.0:
        state = "FAULT_OVER"
    else:
        state = "OK"
    return round(current_ma, 2), state

def current_to_pct(current_ma):
    """4-20mA -> 0~100% 工程量"""
    if current_ma < 3.6:
        return None
    return round((current_ma - 4.0) / 16.0 * 100.0, 1)

# ---------- 2. K 型热电偶线性近似(简化, 仅演示链路) ----------
K_TYPE_MV_PER_C = 0.0410  # mV/℃ 近似(常温段)
def thermo_mv_to_temp(mv, cold_junction_c=25.0):
    """毫伏 -> 温度(简化线性)，加冷端补偿"""
    return round(mv / K_TYPE_MV_PER_C + cold_junction_c, 1)

# ---------- 3. Modbus-RTU CRC16 ----------
def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

def build_modbus_frame(slave, func, reg_addr, value):
    body = bytes([slave, func, reg_addr >> 8, reg_addr & 0xFF,
                  value >> 8, value & 0xFF])
    crc = modbus_crc16(body)
    return body + crc.to_bytes(2, "little")

# ---------- 4. CAN 帧模拟 ----------
def build_can_frame(arb_id, data: bytes):
    return {"id": arb_id, "dlc": len(data), "data": list(data)}

# ---------- 5. 燃烧联锁状态机 ----------
# 状态: IDLE(待机) / PREP(吹扫) / IGNITE(点火) / RUN(运行) / FAULT(故障)
def interlock_step(state, flame_on, air_pressure_ok, valve_cmd):
    """根据现场信号与命令返回 (新状态, 动作列表)"""
    actions = []
    if not air_pressure_ok:
        actions += ["CLOSE_MAIN_VALVE", "CLOSE_PILOT_VALVE", "ALARM"]
        return "FAULT", actions
    if state == "RUN" and not flame_on:
        # 运行中熄火 -> 联锁切断
        actions += ["CLOSE_MAIN_VALVE", "CLOSE_PILOT_VALVE", "ALARM"]
        return "FAULT", actions
    if valve_cmd and air_pressure_ok:
        if state == "PREP":
            return "IGNITE", ["OPEN_PILOT_VALVE"]
        if state == "IGNITE" and flame_on:
            return "RUN", ["OPEN_MAIN_VALVE"]
    return state, actions

# ---------- 演示运行 ----------
if __name__ == "__main__":
    print("== 1. 4-20mA 采集换算 ==")
    for code in [819, 2048, 3276, 200, 3900]:
        cur, st = adc_to_current(code)
        print(f"ADC={code:4d} -> {cur:6.2f}mA  状态={st:11s} 工程量={current_to_pct(cur)}%")

    print("\n== 2. 热电偶(简化) ==")
    for mv in [1.0, 4.1, 8.2]:
        print(f"探头 {mv}mV -> {thermo_mv_to_temp(mv)}℃")

    print("\n== 3. Modbus-RTU 帧 ==")
    frame = build_modbus_frame(slave=1, func=0x06, reg_addr=0x0010, value=100)
    print("发送帧 HEX:", frame.hex(" "))
    crc = modbus_crc16(frame[:-2])
    print("CRC 校验:", "PASS" if crc == int.from_bytes(frame[-2:], "little") else "FAIL")

    print("\n== 4. CAN 帧 ==")
    can = build_can_frame(0x123, bytes([0x01, 0x64]))
    print(can)

    print("\n== 5. 联锁状态机 ==")
    state = "PREP"
    sequence = [
        dict(flame_on=False, air_pressure_ok=True,  valve_cmd=True),
        dict(flame_on=True,  air_pressure_ok=True,  valve_cmd=True),
        dict(flame_on=False, air_pressure_ok=True,  valve_cmd=False),  # 运行中熄火
        dict(flame_on=False, air_pressure_ok=False, valve_cmd=False),  # 风压不足
    ]
    for i, sig in enumerate(sequence, 1):
        state, acts = interlock_step(state, sig["flame_on"], sig["air_pressure_ok"], sig["valve_cmd"])
        print(f"步骤{i}: 状态={state:6s} 动作={acts}")

    print("\n仿真完成：以上结果可记入 07-测试与验证记录；EMC/耐压/温升等待样机实测。")
