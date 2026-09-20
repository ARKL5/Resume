# 详情有活跃文案则补跑 HR 近 3 天

列表卡经常抓不到活跃字（空节点抢在有字的节点前面），空文案不淘汰。点详情后 JSON 的 `activeTimeDesc` 才是准的。有文案且不是近 3 天（在线 / 刚刚 / 今日 / 今天 / 3 日内及更短）则按规则淘汰，不送 JD AI。「进了详情不再跑规则」这条只对标题字面/黑名单/城市成立。已写成保留但活跃不是近 3 天的，下次加载改判到规则，停因写清文案。

**Code**: `boss/src/main/java/com/getjobs/worker/boss/Boss.java`

**Considered Options**: 只修列表抓取、详情仍不跑 HR；列表空活跃直接淘汰。
