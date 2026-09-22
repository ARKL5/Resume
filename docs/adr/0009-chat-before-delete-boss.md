# 代聊迁完再删 boss，对照页分开读两个目录

代聊迁成单独一条命令之后，整份删除 `boss/`。命令接收当场给出的 encryptId，使用同一登录目录；筛选还在跑就拒绝。打开详情后，「立即沟通」发出 yaml 里的招呼语并记已开聊；「继续沟通」不发第二句，记已开聊并跳过。已开聊的跳过。失败和风控不记。两次打开详情的间隔与筛选点 JD 相同，下限 18 秒。发图只在这次命令上当场要，默认不发。对照页没有代聊按钮，也不显示运行状态和等人条。`onRisk: wait` 仍看验证页是否消失。

对照页读 yaml，不再连 `:9527`。`screenResultsDir` 是已筛，续跑只读它。`screenArchiveDir` 是实验目录，只出现在下拉的下一组。正式开跑前不写这个键，结果仍写 `screen-experiments`，`detailLimit` 保持 0。正式开跑时 `screenResultsDir` 改回 `screen-results`，`detailLimit` 改为 -1，并写上 `screenArchiveDir: screen-experiments`。

删除时，yaml、旁边的图简历、已开聊记录、当时已有的正式结果、实验目录挪到仓库根。路径相对 yaml 所在目录。登录目录不搬，用仓库根新的 `browser-data` 重新登录。正式结果当时若为空，根上的 `screen-results` 也为空。

**Code**: `src/boss_screen/chat.py`、`screen/`、`boss.yaml`

**Considered Options**: 代聊不迁就删 Java，以后按 ADR 0006 重做；Python 加只读 HTTP 保住对照页；登录目录原样搬走；实验 jsonl 不留档；现在就把 yaml 指回空的正式目录；两次代聊间隔按 Java 的约 1 秒；图简历这轮不迁；「继续沟通」也再发一遍招呼；对照页写死两个目录名；正式 jsonl 删除时不搬。

**Consequences**: 删掉 `boss/` 后要重新登录。实验目录里的行不进入已筛。正式开跑前的试跑仍写 `screen-experiments`。`sendImgResume` 不驱动代聊。配置、图简历、已开聊、`browser-data`、`screen-results`、`screen-experiments` 都在仓库根，路径相对 `boss.yaml`。
