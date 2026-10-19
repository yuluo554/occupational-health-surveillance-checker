# examples/ 示例输入

**合成输入，不得据此作任何合规或医学结论。** 目录内文件只用于演示 README 的命令句式。

| 文件 | 用途 | 说明 |
|---|---|---|
| `position-sample.json` | `ohscheck plan` / `ohscheck report --position` 的岗位画像输入 | 岗位名与 `position_id` 为虚构；`GBZ188-5.19`（苯作业）在 2025 版规则包中明细已核对（`verified`，在岗期间检查周期 12 个月） |

监护档案侧无需自备输入：仓内已有合成真值库 `data/truth/records/`（72 份，`clean_count: 17`），
可直接喂 `ohscheck scan` / `ohscheck report --directory`——该库**含缺项件，`scan` 退出码 1（检出不符合）属预期**。