# 对照页是本仓独立页

对照页不再挂在 get_jobs 的 Next 壳里，避免被配置中心皮肤带偏。本仓 `screen/` 是独立 Vite 页，打开 `http://localhost:6867`，数据只读 get_jobs `:9527`。get_jobs `/screen` 已删。

**Code**: `screen/`

**Considered Options**: 仍在 get_jobs/front 换皮；仓外第三份目录；对照页跟配置页同一套 ThemeProvider。
