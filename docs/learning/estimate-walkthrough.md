# EKF 实现导游：从公式到 NumPy

这份文档解决的是**语言层**问题：公式长什么样、每个量是什么形状、用 NumPy 怎么写。
它不替你决定实现结构，也不给完整函数。

**用法**：不要通读。卡在哪一步，查对应小节，然后合上文档接着写。
判据不是"看懂了"，是"合上文档能默写出那 5 行"。

配套：`docs/learning/kf_warmup.py`（纯 Python 标量版，先跑它）、
`docs/learning/rewrite-estimation.md`（练习单）、
`docs/architecture/stage-2-single-station-estimation.md` 第 4 节（原始公式）。

---

## 0. 变量表：先记住形状和单位

| 数学符号 | 代码里是什么 | 形状 | 单位 | 谁给的 |
|---|---|---|---|---|
| `x` | `estimate.state.pv` | 6 | m、m/s | 你的估计 |
| `P` | `estimate.covariance` | 6×6 | m²、m²/s²、m²/s | 你的估计 |
| `Φ` | `propagated.transition_matrix` | 6×6 | 无量纲 | Orekit 给你 |
| `Q` | `white_acceleration_noise(...)` | 6×6 | 与 `P` 同单位（m²、m²/s、m²/s²） | 你算 |
| `h(x)` | `measurement.range_m`, `.range_rate_m_s` | 2 | m、m/s | `observations.py` 给你 |
| `H` | `measurement.jacobian` | 2×6 | 混合 | `observations.py` 给你 |
| `z` | `observation.range_m`, `.range_rate_m_s` | 2 | m、m/s | 观测 |
| `R` | 你组的对角阵 | 2×2 | m²、m²/s² | 噪声参数 |
| `y` | `innovation` | 2 | m、m/s | 你算 |
| `S` | 创新协方差 | 2×2 | m²、m²/s² | 你算 |
| `K` | 增益 | **6×2** | 无量纲 | 你算 |
| NIS | 标量 | 1 | 无量纲 | 你算 |

**这条表最重要的一行是 `K` 是 6×2**：它把 2 维观测空间映射回 6 维状态空间。
形状搞错的人，90% 是 `K` 写成了 2×6。

你真正要写的只有：`Q`、`y`、`S`、`K`、`x⁺`、`P⁺`、NIS。
`H` 和 `Φ` 都是别人算好塞给你的。

---

## 1. 三个数学对象

### 1.1 观测模型（不用你写，但要看得懂）

记 `d = r_sat − r_sta`（相对位置），`w = v_sat − v_sta`（相对速度），
`ρ = |d|`，`u = d/ρ`（视线单位向量）：

```text
h₁ = ρ
h₂ = ρ̇ = uᵀ w
```

对状态 `x = [r, v]` 求偏导：

```text
H = [ uᵀ                 0ᵀ ]
    [ (w − ρ̇u)ᵀ / ρ      uᵀ ]
```

第二行第一块的意思是：目标横向移动一点，距离率就变，变化量由「相对速度里垂直于视线的分量」决定。
`observations.py` 里的 `GeometricRangeRateModel.predict` 已经把这两行算好了，直接取 `.jacobian`。

### 1.2 协方差：为什么不能直接比较

`P` 是对称正定矩阵。三个概念：

- **对称**：`P = Pᵀ`。物理上必然成立，数值上可能被舍入破坏。
- **正定**：任意非零向量 `a` 都满足 `aᵀPa > 0`。等价于存在 Cholesky 分解 `P = LLᵀ`。
- **量纲**：位置块约 `1e12`（m²），速度块约 `1e4`（m²/s²），**差 8 个数量级**。

这就是坑：你拿 `np.allclose(P, P.T, atol=1e-12)` 去比，位置块上 `1e12 × 1e-15`（双精度相对误差）
就已经是 `1e-3` 了，合法矩阵会被误杀。

**解法**：先归一化成相关矩阵，把所有元素压到 `[-1, 1]`：

```text
σ = sqrt(diag(P))          # 每维标准差
C = P / (σ σᵀ)             # 相关矩阵，对角线全是 1
```

`C` 对称、正定的判定就与量纲无关了。Cholesky 也建议对 `C` 做，而不是对 `P` 做。

NumPy 写法：

```python
scale = np.sqrt(np.diag(p))          # 注意：np.diag(矩阵) 是「取对角」
correlation = p / np.outer(scale, scale)   # np.outer 造 σ σᵀ
```

`np.diag` 有两副面孔，这是新手最容易懵的地方：

- `np.diag([1, 2, 3])` → 3×3 对角矩阵
- `np.diag(某个矩阵)` → 取出它的对角线

### 1.3 不可变 dataclass 怎么赋值

`StateEstimate` 是 `frozen=True` 的，`self.covariance = ...` 会抛 `FrozenInstanceError`。
标准写法是绕过 `__setattr__`：

```python
object.__setattr__(self, "covariance", value)
```

### 1.4 Q 是从哪来的

假设加速度误差是「连续白噪声」：`E[a(t)a(t')ᵀ] = q δ(t−t') I`，`q` 单位 m²/s³。
在 `Δt` 内，速度误差和位置误差分别是加速度的一次、二次积分：

```text
δv = ∫₀^Δt a(s) ds                 → Var(δv) = q Δt
δr = ∫₀^Δt (Δt−s) a(s) ds          → Var(δr) = q Δt³/3
Cov(δr, δv) = q Δt²/2
```

所以：

```text
Q = q [ Δt³/3 · I₃    Δt²/2 · I₃ ]
      [ Δt²/2 · I₃    Δt   · I₃ ]
```

两件事值得记住：**`Δt³/3` 来自位置的二重积分，`Δt²/2` 来自位置与速度的交叉项。**
`Δt = 0` 时整块为零，这是物理上正确的：没有时间流逝就没有新不确定度。

NumPy 里拼块矩阵：

```python
eye = np.eye(3) * q          # 标量乘整个矩阵
np.block([                   # 注意是「列表的列表」，和矩阵分块写法一一对应
    [eye * dt**3 / 3, eye * dt**2 / 2],
    [eye * dt**2 / 2, eye * dt],
])
```

---

## 2. 逐函数导游

### 2.1 `StateEstimate.__post_init__`

要做的事，按顺序：

1. 把输入转成 float 数组：`p = np.asarray(self.covariance, dtype=float)`
2. 检查 `p.shape == (6, 6)`、`np.isfinite(p).all()`、`np.diag(p) > 0` 全部成立
   （先查对角线，后面要开方，除零会变成 `nan` 或警告）
3. 归一化：`scale = np.sqrt(np.diag(p))`，`correlation = p / np.outer(scale, scale)`
4. 对称性：`np.allclose(correlation, correlation.T, rtol=0.0, atol=1e-12)`
5. 正定性：`np.linalg.cholesky(correlation)`，用 `try/except np.linalg.LinAlgError` 接住，
   转成 `ValueError`
6. 用 `_matrix_tuple(p)`（已给）转成不可变形式，`object.__setattr__` 写回去

坑：

- 第 4 步必须用归一化后的矩阵，否则合法输入被误杀。
- 第 2 步先查有限性再查形状之外的运算，`nan` 会让后面的比较全部为 `False`，报错信息会很难懂。
- 不要 `np.linalg.eigvalsh` 判正定——Cholesky 更快也更稳，而且异常信息清楚。

### 2.2 `diagonal_covariance`

一行数学，两行校验：

1. `require_finite("position_sigma_m", position_sigma_m, positive=True)`，速度同理
2. 造对角阵：位置三个 `σ_r²`，速度三个 `σ_v²`

```python
np.diag([position_sigma_m ** 2] * 3 + [velocity_sigma_m_s ** 2] * 3)
```

最后记得 `_matrix_tuple` 转回契约类型（返回类型标注是 `Matrix6`，即 tuple of tuple）。

### 2.3 `white_acceleration_noise`

1. `dt_s` 和谱密度都要 `require_finite`，且 `dt_s < 0` 或 `spectral_density < 0` 抛 `ValueError`
   （注意：`require_finite` 只管「是不是有限」，不管「是不是非负」，后者你自己查）
2. 按 1.4 节拼块矩阵
3. `_matrix_tuple` 转换

自查：`white_acceleration_noise(0.0, 3.0)` 为什么必须是全零？

### 2.4 `__init__`

1. 校验 `acceleration_psd_m2_s3` 有限、非负
2. 保存 `initial`、`factory`、`model`、`clock`、`_q`
3. 先验状态：`factory.create_linearized(initial).initial_state`
   ——这里只是借用 factory 把 `InitialConditions` 转成 `OrbitState`，这个传播器用完即弃
4. `self._estimate = StateEstimate(先验状态, covariance)`

坑：不要在 `__init__` 里做任何 Orekit 初始化。JVM 由调用方（`initialize_orekit`）负责。

### 2.5 `predict_to`

1. `current = self.estimate`
2. `dt = self._clock.seconds_between(epoch, current.state.epoch)`
   **参数顺序是 `(later, earlier)`，写反了所有观测都会被判成倒序。**
3. `dt < 0` 抛 `ValueError`；`dt == 0` **直接 `return current`**（返回同一个对象，不是新建）
4. 用当前后验重建初值：

   ```python
   initial = replace(
       self._initial,
       epoch=current.state.epoch,
       orbit=current.state.pv,
       mass_kg=current.state.mass_kg,
   )
   ```

5. 传播并拿 Φ：

   ```python
   propagated = self._factory.create_linearized(initial).propagate_with_transition(epoch)
   phi = np.asarray(propagated.transition_matrix)
   ```

6. `p = phi @ np.asarray(current.covariance) @ phi.T`，再加 `Q(dt, self._q)`
7. 对称化：`(p + p.T) / 2`，构造 `StateEstimate`，赋值，返回

为什么必须用**当前**历元重建：`Φ` 是相对传播器参考点的雅可比。用初始历元建的传播器，
`Φ(t₀→t)` 和你需要的 `Φ(tₖ→t)` 不是一回事。

### 2.6 `process`

这是主菜。按顺序，**先把所有量算完，最后一步才提交**：

1. 校验 `observation.spacecraft_id == self.estimate.state.spacecraft_id`
2. 校验 `observation.station_id == self._model.geometry.station.station_id`
3. 预测到观测历元（就是 2.5 的逻辑），得到 `x⁻`、`P⁻`
4. `measurement = self._model.predict(predicted.state)`，取 `h = np.asarray(measurement.jacobian)`
5. 组 `R = np.diag([σ_ρ², σ_ρ̇²])`
6. `y = np.array([z_ρ − h₁, z_ρ̇ − h₂])`
7. `s = h @ p @ h.T + r`
8. `k = np.linalg.solve(s, h @ p).T`

   这一步是全文最容易错的地方。`solve(S, H P)` 解的是 `S X = H P`，得到 `X = S⁻¹ H P`，
   形状 `(2, 6)`。但我们要的 `K = P Hᵀ S⁻¹`，形状 `(6, 2)`。因为 `S`、`P` 都对称：

   ```text
   (S⁻¹ H P)ᵀ = Pᵀ Hᵀ (S⁻¹)ᵀ = P Hᵀ S⁻¹
   ```

   所以**转置一下正好**，而且全程没有显式求逆。

9. `x⁺`：把 `pv` 摊平成 6 维数组，加 `k @ y`，再切回两个三元组
   （用 `tuple(float(v) for v in ...)`，避免 `np.float64` 漏进契约类型）
10.`P⁺`（Joseph）：`a = np.eye(6) - k @ h`，`posterior = a @ p @ a.T + k @ r @ k.T`，再对称化
11. 用**更新后**的状态重算 `h(x⁺)`，得后验残差
12. `nis = float(y @ np.linalg.solve(s, y))`
13. 组装 `FilterUpdate`，**最后**才 `self._estimate = estimate`

第 13 步的顺序就是测试里 `assertIs(ekf.estimate, before)` 要的原子性。

为什么用 Joseph 而不是 `(I − KH)P`：后者在增益很大时容易破坏对称性和正定性，
Joseph 形式在数学上等价，数值上恒正定（两个半正定项相加），再加一次对称化就稳了。

---

## 3. NumPy 最小工具箱

| 要做的事 | 写法 | 注意 |
|---|---|---|
| 转数组 | `np.asarray(x, dtype=float)` | 不复制就直接用；`np.array` 才强制复制 |
| 全有限 | `np.isfinite(a).all()` | 返回 Python `bool`，可 `if` |
| 造对角阵 | `np.diag([a, b])` | 和「取对角」同名，看参数 |
| 取对角 | `np.diag(M)` | |
| 分块拼接 | `np.block([[A, B], [C, D]])` | 每个块都要二维 |
| 外积 | `np.outer(u, v)` = `u vᵀ` | 一维进，二维出 |
| 矩阵乘 | `A @ B` | 链式：`A @ B @ C` |
| 转置 | `A.T` | 一维数组转置是它自己，别对向量用 |
| 解线性系统 | `np.linalg.solve(S, M)` | 别用 `inv`，别用 `*`（那是逐元素） |
| Cholesky | `np.linalg.cholesky(P)` | 失败抛 `LinAlgError` |
| 近似比较 | `np.allclose(A, B, rtol=0.0, atol=1e-12)` | 默认 `rtol` 会掩盖大数值误差 |
| 对称化 | `(P + P.T) / 2` | 每次更新后都做 |
| 摊平 PV | `np.array(pv.position_m + pv.velocity_m_s)` | 元组相加 = 拼接 |
| 标量取出 | `float(x)` | 避免 `np.float64` 进 dataclass |

---

## 4. 手算标量例子（对应 M3 那个测试）

场景：卫星在 `(7_000_000, 0, 0)`，速度 `(100, 0, 0)`；测站在 `(6_000_000, 0, 0)`，静止。
观测：距离 `1_000_020`，距离率 `102`。先验 `P = diag(100, 100, 100, 1, 1, 1)`，`R = diag(25, 0.25)`。

**第 0 步：几何**

```text
d = (1e6, 0, 0)      ρ = 1e6
u = (1, 0, 0)        w = (100, 0, 0)      ρ̇ = uᵀw = 100
w − ρ̇u = 0           → H 第二行第一块全零
```

**第 1 步：H**（只有两个元素非零）

```text
H = [ 1 0 0 0 0 0 ]
    [ 0 0 0 1 0 0 ]
```

**第 2 步：观测预测与创新**

```text
h(x⁻) = (1e6, 100)
y = (1_000_020 − 1e6, 102 − 100) = (20, 2)
```

**第 3 步：S**

```text
H P Hᵀ = diag(100, 1)      S = diag(100+25, 1+0.25) = diag(125, 1.25)
```

**第 4 步：K**（6×2，只有两个非零元素）

```text
K[0][0] = 100/125 = 0.8      K[3][1] = 1/1.25 = 0.8
```

**第 5 步：状态更新**

```text
x⁺[0] = 7_000_000 + 0.8 × 20 = 7_000_016
x⁺[3] = 100 + 0.8 × 2 = 101.6
```

**第 6 步：协方差更新（Joseph）**

```text
A = I − KH      → A[0][0] = 0.2, A[3][3] = 0.2，其余不变
P⁺[0][0] = 0.2² × 100 + 0.8² × 25 = 4 + 16 = 20
P⁺[3][3] = 0.2² × 1  + 0.8² × 0.25 = 0.04 + 0.16 = 0.2
P⁺[1][1] = 100（这一维没被观测，保持不变）
```

**第 7 步：NIS**

```text
NIS = 20²/125 + 2²/1.25 = 3.2 + 3.2 = 6.4
```

这几个数字就是测试断言里的 `7000016.0`、`101.6`、`20.0`、`0.2`、`100.0`、`6.4`。
先在 REPL 里把它们打出来，再跑测试。

**顺带一个重要事实**：这个测试里 `Clock.seconds_between` 对同一历元返回 `0.0`，
所以 `process` 的预测部分是空操作——**M3 不依赖 M2，你可以先写更新**。

---

## 5. 报错对照表

| 症状 | 大概率原因 | 改法 |
|---|---|---|
| `ValueError: 协方差必须对称`，但矩阵看着对称 | 用原始 `P` 比较，位置块 1e12 尺度下浮点误差超 `1e-12` | 先转相关矩阵再比 |
| `LinAlgError` 从 Cholesky 冒出来 | 没接住，或先验本身不 PD | `try/except` 转 `ValueError` |
| `shapes (6,2) and (2,) not aligned` | `K` 忘了 `.T`，变成 2×6 | `solve(s, h @ p).T` |
| 测试 `assertIs` 失败 | `dt == 0` 时新建了 `StateEstimate` | 直接 `return current` |
| 观测全被判成倒序 | `seconds_between` 参数写反 | `(观测历元, 当前历元)` |
| 端到端误差 7 m 变成几百米 | `R` 用了 σ 而不是 σ²；`Q` 的 `Δt` 单位错；`Φ` 用了初始历元 | 对照第 4 节逐项核 |
| 协方差更新后不再正定 | 用了 `(I−KH)P` 且没对称化 | Joseph + `(p+p.T)/2` |
| `AttributeError: _estimate` | `__init__` 没建先验 | `factory.create_linearized(initial).initial_state` |
| 数值全对但很慢 | 每个观测都重建传播器确实慢，但这是当前设计 | 先正确，再谈性能 |

---

## 6. 三条降级路线

1. **先跑 `docs/learning/kf_warmup.py`**。8 行输出看懂「预测加噪声、更新减噪声」的拉锯，再回来看 6 维。
2. **先做 M3**，跳过 M2。上面的标量测试里预测是空操作，更新逻辑可以独立验证。
3. **先在临时文件里写 2 维版本**（两个状态：位置、速度，2×2 矩阵），用 NumPy 跑通同样的 7 步。
   形状从 2×2 长到 6×6 是机械的，别在 6 维里同时调试数学和形状。

---

## 7. 术语小抄

| 词 | 意思 |
|---|---|
| 先验 / 后验 | 用观测之前 / 之后的估计 |
| 创新 `y` | 观测减预测，是「新信息」 |
| 创新协方差 `S` | 预测不确定度 + 测量不确定度 |
| 增益 `K` | 新信息该被信多少，0 到 1 之间（多维时是矩阵） |
| NIS | `yᵀS⁻¹y`，归一化创新平方；一致时均值 ≈ 1 |
| 一致（consistent） | 估计误差的统计特性符合它自己声称的协方差 |
| STM `Φ` | 状态转移矩阵，把初值扰动线性映射到末值扰动 |
| 3σ 椭球 | 协方差特征值开方 × 3 画出来的不确定区域 |
