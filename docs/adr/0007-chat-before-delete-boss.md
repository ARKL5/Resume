# 代聊单独命令，对照页只读目录

代聊接收当场给出的 encryptId，与筛选共用登录目录。筛选还在跑就拒绝。「立即沟通」发出 `greeting` 并记已开聊；「继续沟通」只记已开聊，不发第二句。已开聊的跳过。失败和风控不记。发图只在这次命令上当场要。两次打开详情的间隔与筛选点详情相同。对照页没有代聊，也不显示运行状态。

对照页读 `boss.yaml`。`screenResultsDir` 是已筛那一组；写了 `screenArchiveDir` 时，实验目录只出现在下拉的下一组。

**Code**: `src/boss_screen/chat.py`、`screen/screen-data.mjs`

**Considered Options**: 对照页走 HTTP；「继续沟通」再发一遍招呼；目录名写死在页面里。
