# -*- coding: utf-8 -*-
"""
电路级仿真（纯 Python，不依赖 LTspice/scipy，0 成本）
模块 A：4-20mA I/V 采集链路 —— 250Ω 采样 + RC 低通 + 跟随 + 分压，直流工作点与阶跃响应
模块 B：24V 电源输入级 —— 防反接、TVS 钳位、π 型滤波、LDO 后级直流工作点
说明：本脚本为原理级电路仿真，用于作品集记录；真实纹波/瞬态需 LTspice 或样机实测。
"""
import numpy as np

# ============ 模块 A：4-20mA I/V 链路 ============
# 链路: 电流源 I -> R_s=250Ω -> 节点 V_s(1~5V) -> RC低通(Rf,Cf) -> 跟随器 -> 分压 -> ADC(0~3.3V)
R_S = 250.0
R_F = 1.0e3          # 滤波电阻 1k
C_F = 100.0e-9       # 滤波电容 100nF -> 截止 fc≈1.59kHz
R_DIV1, R_DIV2 = 10.0e3, 16.5e3   # 分压: 5V*R_DIV2/(R_DIV1+R_DIV2)≈3.13V
ADC_VREF = 3.3
ADC_FULL = 4095

def divider_ratio():
    return R_DIV2 / (R_DIV1 + R_DIV2)

def iv_chain_dc(current_ma):
    """直流工作点：返回采样电压、滤波后电压、ADC 输入电压、ADC 码值"""
    i = current_ma / 1000.0
    v_sensor = i * R_S                       # 1~5V
    v_filter = v_sensor                      # 直流下电容开路，滤波不衰减
    v_adc = v_filter * divider_ratio()
    code = int(round(v_adc / ADC_VREF * ADC_FULL))
    return v_sensor, v_filter, v_adc, code

def iv_step_response(i_step_ma, t_end=0.01, dt=1e-5):
    """电流阶跃后 RC 低通的时域响应（一阶 RC）"""
    tau = R_F * C_F
    t = np.arange(0, t_end, dt)
    v_final = i_step_ma / 1000.0 * R_S * divider_ratio()
    v = v_final * (1 - np.exp(-t / tau))
    return t, v, tau

print("== 模块A：4-20mA I/V 链路 直流工作点 ==")
print(f"分压比={divider_ratio():.3f}  RC 时间常数 τ={R_F*C_F*1e6:.1f}µs  截止 fc={1/(2*np.pi*R_F*C_F):.0f}Hz")
for ma in [4.0, 12.0, 20.0]:
    vs, vf, va, code = iv_chain_dc(ma)
    print(f"  {ma:4.1f}mA -> 采样 {vs:.2f}V | 滤波后 {vf:.2f}V | ADC入 {va:.2f}V | 码值 {code}")

print("\n== 模块A：20mA 阶跃响应（建立时间） ==")
t, v, tau = iv_step_response(20.0)
v_target = 20.0/1000.0*R_S*divider_ratio()
# 到达 90% / 99% 稳定值的时间
t90 = -tau*np.log(1-0.90); t99 = -tau*np.log(1-0.99)
print(f"  目标 ADC 电压 {v_target:.2f}V；τ={tau*1e6:.1f}µs；到 90% ≈ {t90*1e6:.1f}µs，到 99% ≈ {t99*1e6:.1f}µs")

# ============ 模块 B：24V 电源输入级 ============
V_IN_NOM = 24.0
TVS_VBR = 26.0        # SMBJ24A 典型击穿/钳位参考
FUSE_I = 2.0          # 自恢复保险 2A
# 防反接: 理想 MOS(压降忽略)；反接时截止。π 型滤波: L + 两个电容(直流开路)
def input_stage_dc(v_in):
    # 反接判断
    if v_in < 0:
        return 0.0, "REVERSE_BLOCKED"
    # TVS 钳位：超过击穿电压则被钳到近似钳位电压
    v_clamp = min(v_in, TVS_VBR + 2.0)
    # 后级 DC-DC 前直流电压（π 滤波直流压降忽略）
    return v_clamp, "OK"

print("\n== 模块B：24V 输入级 直流工作点 ==")
for vin in [18.0, 24.0, 30.0, 36.0, -24.0]:
    v_out, st = input_stage_dc(vin)
    print(f"  输入 {vin:6.1f}V -> 后级 {v_out:5.2f}V  状态={st}")

# LDO: 5V->3.3V，压差与负载
U5V, U33, DROPOUT = 5.0, 3.3, 0.2
print(f"\n  LDO: {U5V}V -> {U33}V，压差 {U5V-U33:.1f}V >  dropout {DROPOUT}V，满足稳压条件")

# ============ 判据汇总 ============
print("\n== 仿真判据 ==")
checks = []
vs4, _, va4, _ = iv_chain_dc(4.0)
vs20, _, va20, _ = iv_chain_dc(20.0)
checks.append(("4mA 采样=1.00V", abs(vs4-1.0)<0.01))
checks.append(("20mA 采样=5.00V", abs(vs20-5.0)<0.01))
checks.append(("ADC 输入不超 3.3V", va20 < ADC_VREF))
_, st_rev = input_stage_dc(-24.0)
checks.append(("反接被阻断", st_rev=="REVERSE_BLOCKED"))
checks.append(("LDO 压差满足", (U5V-U33)>=DROPOUT))
for name, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
