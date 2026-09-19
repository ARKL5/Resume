# 对照页是本仓独立圈阅页

对照页不再挂在 get_jobs 的 Next 壳里，避免被配置中心皮肤带偏。本仓 `screen/` 是独立 Vite 页：浅色冷灰纸面，朱砂只给已圈（○/●），岗位名墨色下划线仍是 Boss 链接，停因宋体。人机验证条可用朱砂边。打开 `http://localhost:6867`，数据仍读 get_jobs `:9527`。get_jobs `/screen` 已删。

**Code**: `screen/`

**Considered Options**: 仍在 get_jobs/front 换皮；仓外第三份目录；对照页跟配置页同一套 ThemeProvider。
