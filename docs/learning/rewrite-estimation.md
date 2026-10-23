# 重写练习：`ssa/estimation.py`

## 为什么只重写这一个文件

146 行，是全仓库唯一的科学内核。`domain.py` 是类型定义，`observations.py` 是几何公式，
`ssa/orekit/` 是黑盒适配层——它们都能靠读和查解决。只有 EKF 你必须"会"，因为它决定了
后面所有阶段（协方差收缩、融合、调度收益）的物理含义。

重写它的目的不是产出更好的代码，是让这套数学变成**你能预测**的东西：
改 `q` 会怎样、换噪声会怎样、观测稀疏时会怎样。

## 工作区

```bash
git switch rewrite-estimation    # 当前分支（脚手架已就位）
git switch main                  # 随时回到原始完成态对照
git diff main -- ssa/estimation.py   # 看你的版本与原版的差异
```

原始实现在 git 历史里，不会丢。**但请先不要看**，见下面的提示阶梯。

## 四条规则

1. **不改 `tests/`**。测试是规格；测试红了，改代码，不改断言。
2. **一次只让一个测试变绿**。从 M1 开始，按顺序来。
3. **每个函数先在 REPL 里用手算数字验证**，通过了再跑测试。测试失败信息不如手算直观。
4. **卡住超过 20 分钟才升一级提示**，升之前把当前思路写在纸上。

另外 4 个用例（Jacobian 差分、可见性与种子、STM 对照、测站自转）完全不碰 `estimation.py`。
它们在重写全程都该是绿的——哪天红了，说明你改坏了别的文件，这是你的护栏。

## 配套材料

| 文件 | 什么时候用 |
|---|---|
| `docs/learning/kf_warmup.py` | 开始前跑一次，看「预测加噪声、更新减噪声」的拉锯。纯 Python，无矩阵 |
| `docs/learning/estimate-walkthrough.md` | 卡在具体某一步时查：形状表、NumPy 对照、手算数字、报错对照表 |
| `docs/architecture/stage-2-single-station-estimation.md` §4 | 原始公式，最权威 |

导游文档按需查，**不要通读**。看懂了不算数，合上能默写才算。

## 四个里程碑

预计总时长 **6–8 小时**，拆成四个半天。每步都有明确的"绿"。

### M1：协方差的不变量（约 1 小时）

要写：`StateEstimate.__post_init__`、`diagonal_covariance`、`white_acceleration_noise`

```bash
uv run python -m unittest discover -s tests -p "test_estimation.py" -k "covariance_and_configuration" -k "white_acceleration" -v
```

关键不变量：

- 位置块约 `1e12`（m²），速度块约 `1e4`（m²/s²），**差 8 个数量级**。直接拿 `atol=1e-12`
  比 `P` 和 `P.T` 会误杀合法矩阵——你需要先选一个与量纲无关的尺度。
- `np.ones((6,6))` 必须被拒（它不是正定）；`np.eye(6) + np.diag([2.0]*5, 1)` 必须被拒（非对称）。
- 构造后改外部 `np.ndarray`，实例内部值不能变。

自查：

- 为什么用 Cholesky 而不是 `det > 0` 判断正定？
- `white_acceleration_noise(0.0, 3.0)` 为什么必须是全零？`q=0` 的默认示例靠这个。

### M2：预测（约 2 小时）

要写：`__init__`、`predict_to`

```bash
uv run python -m unittest discover -s tests -p "test_estimation.py" -k "prediction_gaps" -v
```

关键不变量：

- 同历元返回 `self.estimate` **本身**（测试用的是 `assertIs`，不是 `assertEqual`）。
- `P⁻ = Φ P⁺ Φᵀ + Q(Δt)`；`Φ` 必须相对**当前估计历元**，不是初始历元。
- 先验估计来自 `factory.create_linearized(initial).initial_state`。

自查：

- 为什么每次预测要重建传播器，而不是复用同一个实例？
- `seconds_between` 为什么不能直接减 `datetime`？

### M3：更新（约 2 小时）

要写：`process`

```bash
uv run python -m unittest discover -s tests -p "test_estimation.py" -k "scalar_kalman" -v
```

这个测试是标量解析解，所有数字能手算——先在纸上算一遍，再写代码。

关键不变量：

- 线性系统用 `numpy.linalg.solve`，不显式求逆。
- 协方差更新用 Joseph 形式并对称化，保证正定性不被舍入破坏。
- `postfit_residual` 用**更新后**状态的 `h(x⁺)` 重算，不是复用先验创新。
- 任一校验失败时 `self.estimate` 保持调用前那个对象（`assertIs`）。

自查：

- 先验创新和后验残差的区别是什么？为什么残差 RMS 检验要用后者？
- NIS 期望值是多少？超过多少说明滤波器过度自信？

### M4：端到端（约 1 小时）

```bash
uv run python -m unittest discover -s tests -v
uv run python orbit_determination.py --seed 42
```

对照 README / 阶段 2 文档里的参考输出：

| 指标 | 参考值 |
|---|---|
| 可见观测 | 86 组 |
| 末次位置 / 速度误差 | 7.297 m / 0.012304 m/s |
| 末次位置标准差 RSS | 5.728 m |
| 后验测距 / 距离率残差 RMS | 7.667 m / 0.085913 m/s |

数值应当高度一致（浮点运算顺序不同可能有末位差异）。**对不上说明物理搞错了，不是代码风格问题。**

## 提示阶梯

按顺序解锁，每级至少花 20 分钟：

1. **数据形状与单位**：`estimate-walkthrough.md` 第 0 节的变量表。把 `x, P, Φ, Q, H, R, y, S, K` 的形状抄一遍。
2. **六行公式**：`docs/architecture/stage-2-single-station-estimation.md` 第 4 节。
3. **数学推导**：`estimate-walkthrough.md` 第 1 节（协方差为什么归一化、Q 的 `Δt³/3` 从哪来）。
4. **逐函数步骤**：`estimate-walkthrough.md` 第 2 节——给的是步骤和关键表达式，不是完整函数。
5. **手算对照**：`estimate-walkthrough.md` 第 4 节，把标量例子的数字先在 REPL 里打出来。
6. **参考实现**：`git show main:ssa/estimation.py`。看过之后合上，隔 10 分钟再手写一遍。

## 卡住时问自己三句话

1. 这个函数的输入输出，单位和坐标系分别是什么？
2. 哪个不变量是"即使数值算对也不能破"的？（对称、正定、时间单向、原子性）
3. 如果删掉我刚写的 5 行，哪个测试会红？

## 完成判据

- [ ] `uv run python -m unittest discover -s tests -v` → 21 个测试全绿
- [ ] 端到端指标与参考表一致
- [ ] 文件顶部的"重写练习脚手架"注释换成**你自己的一句话**：这个文件删了会坏什么
- [ ] `git diff main -- ssa/estimation.py` 的每一处差异，你都能解释
- [ ] M1–M4 的自查问题，答案写下来（一句话也行）

做完之后，`ssa/estimation.py` 是全仓库第一个"你的"文件。剩下的文件按同样的方式逐个认领，
顺序建议：`observations.py`（几何）→ `propagation.py`（端口）→ `ssa/orekit/stations.py`（测站）。
