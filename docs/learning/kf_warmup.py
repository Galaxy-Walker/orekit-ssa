"""一维标量 Kalman：把「预测 → 创新 → 增益 → 更新」跑成肌肉记忆。

纯 Python，没有 NumPy，没有矩阵。目的不是算准，是让每一步的含义变成本能。
对照 `docs/learning/estimate-walkthrough.md` 第 2.6 节，再看 `ssa/estimation.py` 的 6 维版本，
只是把数字换成矩阵、把除法换成 `np.linalg.solve`。

运行：uv run python docs/learning/kf_warmup.py
"""

# 真值：目标固定在 x = 10 m 处；传感器 σ = 3 m，读数在真值附近随机散布
MEASUREMENTS = [11.2, 6.5, 13.4, 9.8, 12.1, 7.3, 10.9, 10.2]

estimate = 0.0       # x⁻：先验位置估计（m），故意从错的 0 开始
variance = 25.0      # P：先验方差（m²），σ = 5 m
process_noise = 0.5  # Q：每次预测增加的不确定度（m²）
measurement_noise = 9.0  # R：传感器方差（m²），σ = 3 m

print(f"{'step':>4} {'z':>6} {'y':>7} {'S':>7} {'K':>7} {'x+':>7} {'P+':>6} {'NIS':>6}")
for step, measurement in enumerate(MEASUREMENTS, start=1):
    # 1. 预测：没有动力学，状态原样；不确定度只会增加
    variance = variance + process_noise

    # 2. 创新：测量减预测。y 是「新信息」，也是先验误差的代理
    innovation = measurement - estimate

    # 3. 创新协方差：预测的不确定度 + 测量的不确定度
    innovation_variance = variance + measurement_noise

    # 4. 增益：预测越不确定、测量越可信，K 越接近 1
    gain = variance / innovation_variance

    # 5. 状态更新：按增益把估计往测量方向拉
    estimate = estimate + gain * innovation

    # 6. 协方差更新：标量 Joseph 形式，和 6 维里的 A P Aᵀ + K R Kᵀ 是同一件事
    variance = (1.0 - gain) ** 2 * variance + gain ** 2 * measurement_noise

    # 7. NIS：归一化创新平方。理想情况下均值应接近 1
    nis = innovation * innovation / innovation_variance

    print(
        f"{step:>4} {measurement:>6.2f} {innovation:>7.2f} {innovation_variance:>7.2f}"
        f" {gain:>7.3f} {estimate:>7.3f} {variance:>6.3f} {nis:>6.3f}"
    )

print()
print("观察三件事：")
print("1. K 随 P 收缩而变小 —— 估计越确定，越不轻信新测量。")
print("2. P 下降后停在平衡值附近 —— 预测加噪声、更新减噪声，两者拉锯。")
print("3. NIS 的量级和 1 比 —— 长期均值应接近 1；这里只有 8 个样本，")
print("   且第 1 步先验偏差 10 m 本就很大，所以早期偏大、后面偏小都是正常的。")
print("   阶段 2 端到端有 86 组观测，才谈得上统计意义。")
