package com.getjobs.worker.boss;

import com.getjobs.application.service.AiService;
import com.getjobs.application.service.BossService;
import com.getjobs.worker.HumanAttention;
import com.getjobs.worker.utils.Job;
import com.getjobs.worker.utils.JobUtils;
import com.getjobs.worker.utils.PlaywrightUtil;
import com.microsoft.playwright.Locator;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Response;
import lombok.RequiredArgsConstructor;
import lombok.Setter;
import lombok.SneakyThrows;
import lombok.extern.slf4j.Slf4j;
import org.json.JSONObject;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.*;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;

import static com.getjobs.worker.boss.Locators.*;


/**
 * @author loks666
 * 项目链接: <a href=
 * "https://github.com/loks666/get_jobs">https://github.com/loks666/get_jobs</a>
 * Boss直聘自动投递
 */
@Slf4j
@Component
@Scope("prototype")
@RequiredArgsConstructor
public class Boss {

    @Setter
    private Page page;
    @Setter
    private BossConfig config;
    private final BossService bossService;
    private final AiService aiService;
    private final HumanAttention humanAttention;
    private final com.getjobs.application.service.LocalBossSettings localBossSettings;
    private Set<String> blackCompanies;
    private Set<String> blackRecruiters;
    private Set<String> blackJobs;
    // 记录 encryptId -> encryptUserId 的映射，用于后续更新投递状态
    private final ConcurrentMap<String, String> encryptIdToUserId = new ConcurrentHashMap<>();
    @Setter
    private ProgressCallback progressCallback;
    @Setter
    private Supplier<Boolean> shouldStopCallback;

    private final List<Job> resultList = new ArrayList<>();

    /** Boss 首页，UI 搜索的入口 */
    private static final String BOSS_HOME_URL = "https://www.zhipin.com";
    /**
     * true=先回首页、在搜索框里做一次真实 UI 搜索再进列表页；false=直接拼 URL 跳转。
     * <p>
     * 默认关掉。实测 Boss 首页在受控标签页里会一直转圈加载不完，navigate 要 60 秒才返回，
     * 期间 evaluate / locator 全部无限期阻塞（这两个 API 没有默认超时）—— 启动慢、投递卡死、
     * 管理页面按钮没反应都出在这。而岗位列表页在同一个浏览器里是秒开的。
     * 想重新试 UI 搜索路径时再打开。
     */
    private static final boolean USE_UI_SEARCH = false;
    /** 等待页面加载状态的超时（毫秒），绝不能不设 —— 见 waitForPageSettled 的说明 */
    private static final double LOAD_STATE_TIMEOUT = 10_000;
    /** true=只读岗并用 AI 筛选，不点立即沟通。本轮先看名单。 */
    private static final boolean SCREEN_ONLY = true;
    /** 「训练」不含「后训练」。字面列表在 boss.yaml rules。 */
    /** 滚动懒加载每轮等待（秒）。 */
    private static final int SCROLL_SLEEP_SECONDS = 2;
    /** 信息已到手后的 AI 并行度。不加速 Boss 点详情。 */
    private static final int AI_PARALLELISM = 32;
    private static String candidateProfile;
    /** 当前卡片 HR 活跃文案，写入 jsonl。 */
    private String lastHrActive = "";
    /** 一岗一行，key=id:encryptId，没有 ID 才用 name:公司|岗位。 */
    private final Map<String, JSONObject> screenRows = new LinkedHashMap<>();
    /** 终局已筛，再跑跳过（不问 AI、不点详情）。 */
    private final Set<String> skipTerminalKeys = new HashSet<>();
    /** 仅因 HR 不活跃被规则淘汰，下次卡片近 3 天则重开。 */
    private final Set<String> hrDropKeys = new HashSet<>();
    /** 过了标题 AI、杭州/上海、还没点到详情。 */
    private final Set<String> pendingDetailKeys = new HashSet<>();
    /** 其它城市过了标题 AI，本轮不点详情。 */
    private final Set<String> otherCityPendingKeys = new HashSet<>();
    /** 连续读不到公司/岗位名：人机验证挡在列表上时 URL 往往不变。 */
    private int emptyDetailStreak = 0;
    /** 列表接口里的活跃文案，encryptId -> activeTimeDesc。被动听，不自己请求。 */
    private final Map<String, String> listJsonActive = new ConcurrentHashMap<>();
    /** 一次开始筛选已占用的详情次数（跨词、跨城）。 */
    private int detailClicksReserved = 0;
    private boolean listJsonHooked = false;

    /**
     * 进度回调接口
     */
    @FunctionalInterface
    public interface ProgressCallback {
        void accept(String message, Integer current, Integer total);
    }

    // 通过 Lombok @RequiredArgsConstructor 使用构造器注入 bossService 与 aiService

    public void prepare() {
        this.blackCompanies = bossService.getBlackCompanies();
        this.blackRecruiters = bossService.getBlackRecruiters();
        this.blackJobs = bossService.getBlackJobs();

        log.info("黑名单加载完成: 公司({}) 招聘者({}) 职位({})",
                blackCompanies != null ? blackCompanies.size() : 0,
                blackRecruiters != null ? blackRecruiters.size() : 0,
                blackJobs != null ? blackJobs.size() : 0);
        // 不在页面初始化阶段入库，仅用于后续点击卡片时按需入库
    }

    /**
     * 执行投递
     */
    public int execute() {
        beginFreshRun();
        hookListJsonOnce();
        List<String> cityCodes = config.getCityCode();
        for (int ci = 0; ci < cityCodes.size(); ci++) {
            if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                progressCallback.accept("用户取消投递", 0, 0);
                break;
            }
            postJobByCity(cityCodes.get(ci));
            if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                progressCallback.accept("用户取消投递", 0, 0);
                break;
            }
            if (ci < cityCodes.size() - 1) {
                waitKeywordGap();
            }
        }
        return resultList.size();
    }

    /**
     * 获取结果列表
     */
    public List<Job> getResultList() {
        return new ArrayList<>(resultList);
    }

    /**
     * 更新黑名单（从聊天记录中）
     */
    public Map<String, Set<String>> updateBlacklistFromChats() {
        page.navigate("https://www.zhipin.com/web/geek/chat");
        PlaywrightUtil.sleep(3);

        int newBlacklistCount = 0;
        boolean shouldBreak = false;
        while (!shouldBreak) {
            try {
                Locator bottomLocator = page.locator(FINISHED_TEXT);
                if (bottomLocator.count() > 0 && "没有更多了".equals(bottomLocator.textContent())) {
                    shouldBreak = true;
                }
            } catch (Exception ignore) {
            }

            Locator items = page.locator(CHAT_LIST_ITEM);
            int itemCount = items.count();

            for (int i = 0; i < itemCount; i++) {
                try {
                    Locator companyElements = page.locator(COMPANY_NAME_IN_CHAT);
                    Locator messageElements = page.locator(LAST_MESSAGE);

                    if (i >= companyElements.count() || i >= messageElements.count()) {
                        break;
                    }

                    String companyName = null;
                    String message = null;
                    int retryCount = 0;

                    while (true) {
                        try {
                            companyName = companyElements.nth(i).textContent();
                            message = messageElements.nth(i).textContent();
                            break;
                        } catch (Exception e) {
                            retryCount++;
                            if (retryCount >= 2) {
                                log.info("尝试获取元素文本2次失败，放弃本次获取");
                                break;
                            }
                            log.info("页面元素已变更，正在重试第{}次获取元素文本...", retryCount);
                            PlaywrightUtil.sleep(1);
                        }
                    }

                    if (companyName != null && message != null) {
                        boolean match = message.contains("不") || message.contains("感谢") || message.contains("但")
                                || message.contains("遗憾") || message.contains("需要本") || message.contains("对不");
                        boolean nomatch = message.contains("不是") || message.contains("不生");
                        if (match && !nomatch) {
                            if (blackCompanies.stream().anyMatch(companyName::contains)) {
                                continue;
                            }
                            companyName = companyName.replaceAll("\\.{3}", "");
                            if (companyName.matches(".*(\\p{IsHan}{2,}|[a-zA-Z]{4,}).*")) {
                                blackCompanies.add(companyName);
                                // 保存到数据库
                                bossService.addBlacklist("company", companyName);
                                newBlacklistCount++;
                                log.info("黑名单公司：【{}】，信息：【{}】", companyName, message);
                            }
                        }
                    }
                } catch (Exception e) {
                    log.error("寻找黑名单公司异常...", e);
                }
            }

            try {
                Locator scrollElement = page.locator(SCROLL_LOAD_MORE);
                if (scrollElement.count() > 0) {
                    scrollElement.scrollIntoViewIfNeeded();
                } else {
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);");
                }
            } catch (Exception e) {
                log.error("滚动元素出错", e);
                break;
            }
        }
        log.info("黑名单公司数量：{}，本次新增：{}", (blackCompanies != null ? blackCompanies.size() : 0), newBlacklistCount);

        Map<String, Set<String>> result = new HashMap<>();
        result.put("blackCompanies", new HashSet<>(blackCompanies != null ? blackCompanies : Collections.emptySet()));
        result.put("blackRecruiters", new HashSet<>(blackRecruiters != null ? blackRecruiters : Collections.emptySet()));
        result.put("blackJobs", new HashSet<>(blackJobs != null ? blackJobs : Collections.emptySet()));
        return result;
    }

    private void postJobByCity(String cityCode) {
        loadScreenState();
        String searchUrl = getSearchUrl(cityCode);
        List<String> keywords = config.getKeywords();
        for (int ki = 0; ki < keywords.size(); ki++) {
            String keyword = keywords.get(ki);
            // 检查是否需要停止
            if (shouldStopCallback.get()) {
                progressCallback.accept("用户取消投递", 0, 0);
                return;
            }

            int postCount = 0;
            // 使用 URLEncoder 对关键词进行编码
            String encodedKeyword = URLEncoder.encode(keyword, StandardCharsets.UTF_8);

            String url = searchUrl + (searchUrl.contains("?") ? "&" : "?") + "query=" + encodedKeyword;
            // 单个关键词失败不该让整个投递任务中止，下面整段都包在 try 里
            try {
            // 进列表页 + 等列表渲染，整段带重试
            openJobListWithRetry(keyword, url, cityCode);

            // 1. 滚到真正到底，边滚边收下卡片文本（列表可能虚拟化，滚完 DOM 里只剩末屏）
            Map<String, CardPreview> harvested = new LinkedHashMap<>();
            harvestVisibleCards(keyword, harvested);
            int lastHarvested = harvested.size();
            int stableTries = 0;
            int staleHits = 0;
            // 上限 300 轮：原来写的是 5000，而且 stableTries 只触发强制触底、从不退出循环，
            // 一旦 footer 选择器匹配不到就会空转几千轮，每轮一次 evaluate + count，
            // 能把 playwright 线程占死几十分钟 —— 整个应用跟着卡住、投递任务也永远结束不了。
            boolean loadedAll = false;
            for (int i = 0; i < 300; i++) {
                // 停止检查：滚动加载过程中也要及时响应
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    progressCallback.accept("用户取消投递", 0, 0);
                    return;
                }
                // 滚动加载期间 Boss 会频繁增删 frame，Playwright 派发这些事件时可能
                // 引用到已销毁的 frame（Object doesn't exist: frame@...），异常会顺着
                // 当时在飞的那个调用抛出来。这类异常和调用本身无关，跳过这一轮继续滚就行。
                try {
                    if (pageNeedsHuman()) {
                        waitForHuman("Boss 滚动列表时弹出人机验证或登录。请到 Boss 拉起的 Chrome 处理。");
                    }
                    // footer 可见不能立刻就当作"加载完了"：窗口最大化时首屏很短，
                    // 第一轮 footer 就是可见的。到底看已收获张数是否还在增加，
                    // 不看当前 DOM 张数（虚拟化时可见卡片常年约 15）。
                    page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 1.5))");
                    PlaywrightUtil.sleep(SCROLL_SLEEP_SECONDS);
                    harvestVisibleCards(keyword, harvested);

                    int currentHarvested = harvested.size();
                    if (currentHarvested == lastHarvested) {
                        stableTries++;
                    } else {
                        stableTries = 0;
                    }
                    lastHarvested = currentHarvested;
                    log.info("【{}】滚动第{}轮，已收获{}条", keyword, i + 1, currentHarvested);
                    if (progressCallback != null && i % 5 == 0) {
                        progressCallback.accept("滚动列表 " + keyword + " 已收获 " + currentHarvested, i + 1, 300);
                    }

                    if (stableTries >= 3) {
                        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)");
                        PlaywrightUtil.sleep(SCROLL_SLEEP_SECONDS);
                        harvestVisibleCards(keyword, harvested);
                        if (harvested.size() > lastHarvested) {
                            stableTries = 0;
                            lastHarvested = harvested.size();
                        }
                    }

                    boolean footerVisible = false;
                    Locator footer = page.locator("div#footer, #footer");
                    if (footer.count() > 0 && footer.first().isVisible()) {
                        footerVisible = true;
                    }
                    if (i >= 5 && footerVisible && stableTries >= 2) {
                        log.info("【{}】已滚动到底部且连续 {} 轮无新增收获，判定加载完毕，共{}条",
                                keyword, stableTries, harvested.size());
                        loadedAll = true;
                        break;
                    }
                    if (i >= 5 && stableTries >= 8) {
                        log.info("【{}】连续 {} 轮没有新增收获，判定已加载完毕，共{}条",
                                keyword, stableTries, harvested.size());
                        loadedAll = true;
                        break;
                    }
                } catch (Exception e) {
                    if (!isStaleObjectError(e)) {
                        throw e;
                    }
                    staleHits++;
                    if (staleHits > 20) {
                        log.warn("【{}】滚动期间反复出现失效对象异常({}次)，停止继续加载", keyword, staleHits);
                        break;
                    }
                    PlaywrightUtil.sleep(1);
                }
            }
            if (!loadedAll) {
                log.warn("【{}】滚动到达 300 轮上限仍未确认加载完毕，按当前已加载的岗位继续", keyword);
            }
            harvestVisibleCards(keyword, harvested);
            int loadedCount = harvested.size();
            log.info("【{}】岗位已全部加载，去重后{}条", keyword, loadedCount);
            progressCallback.accept("岗位加载完成：" + keyword, 0, loadedCount);

            page.evaluate("window.scrollTo(0, 0);");
            PlaywrightUtil.sleep(1);

            List<CardPreview> allCards = new ArrayList<>(harvested.values());
            List<CardPreview> worthClick = new ArrayList<>();
            List<CardPreview> needTitleAi = new ArrayList<>();
            int iCard = 0;
            for (CardPreview preview : allCards) {
                iCard++;
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    progressCallback.accept("用户取消投递", iCard, allCards.size());
                    return;
                }
                String listKey = previewKey(preview);
                String cityPage = classifyCity(preview.area);
                if (skipTerminalKeys.contains(listKey)) {
                    log.info("跳过已终局 | {} | {} | {}", preview.encryptId, preview.company, preview.job);
                    continue;
                }
                if (otherCityPendingKeys.contains(listKey) && !isSearchCity(cityPage)) {
                    log.info("跳过其它城市待读 | {} | {}", preview.company, preview.job);
                    continue;
                }
                String listActive = effectiveActive(preview, listKey);
                CardPreview forRules = listActive.equals(nullToEmpty(preview.active))
                        ? preview
                        : new CardPreview(preview.job, preview.company, preview.area, listActive,
                                preview.href, preview.encryptId);
                if (hrDropKeys.contains(listKey) && !isActiveWithin3Days(listActive)) {
                    writePreviewStage(keyword, forRules, "rule_drop",
                            ruleReasonLabel("HR未近3天活跃：" + listActive), true);
                    continue;
                }
                if (pendingDetailKeys.contains(listKey) || otherCityPendingKeys.contains(listKey)) {
                    log.info("跳过已待读 | {} | {} | {}", preview.encryptId, preview.company, preview.job);
                    continue;
                }
                String listRule = ruleDropReason(forRules.job, forRules.company, forRules.active);
                if (listRule != null) {
                    boolean hrDrop = listRule.startsWith("HR未近3天");
                    writePreviewStage(keyword, forRules, "rule_drop",
                            ruleReasonLabel(listRule), hrDrop);
                    continue;
                }
                needTitleAi.add(preview);
            }
            List<AiOutcome> titleAiOut = runAiParallel("标题AI", needTitleAi.size(),
                    () -> needTitleAi.stream()
                            .map(preview -> (Callable<AiOutcome>) () -> listTriageByTitle(keyword, preview))
                            .toList());
            int remainingClicks = resolveDetailLimit() - detailClicksReserved;
            for (int i = 0; i < needTitleAi.size(); i++) {
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    progressCallback.accept("用户取消投递", i, needTitleAi.size());
                    return;
                }
                CardPreview preview = needTitleAi.get(i);
                AiOutcome outcome = i < titleAiOut.size() ? titleAiOut.get(i)
                        : AiOutcome.fail("标题AI未返回");
                String cityPage = classifyCity(preview.area);
                if (outcome.title == null) {
                    writePreviewStage(keyword, preview, "ai_title_pending",
                            aiTitleFailReason(outcome.reason), false);
                    continue;
                }
                if (outcome.title == TitleAction.DROP) {
                    writePreviewStage(keyword, preview, "ai_title_drop",
                            aiTitleReasonLabel(outcome.reason), false);
                    continue;
                }
                if (!isSearchCity(cityPage)) {
                    writePreviewStage(keyword, preview, "jd_wait_other",
                            aiTitleReasonLabel(outcome.reason) + "；工作地「" + cityPage + "」，本轮不点详情", false);
                    continue;
                }
                if (outcome.title == TitleAction.PARK) {
                    writePreviewStage(keyword, preview, "jd_wait",
                            aiTitleReasonLabel(outcome.reason), false);
                    continue;
                }
                String clickReason = aiTitleReasonLabel(outcome.reason);
                if (remainingClicks > 0) {
                    writePreviewStage(keyword, preview, "jd_wait", clickReason, false);
                    worthClick.add(preview);
                    remainingClicks--;
                    detailClicksReserved++;
                } else {
                    writePreviewStage(keyword, preview, "jd_wait",
                            clickReason + "；本轮详情上限", false);
                }
            }
            log.info("【{}】列表{}张，本词点详情{}张（本次已占{}/上限{}）",
                    keyword, allCards.size(), worthClick.size(),
                    detailClicksReserved, resolveDetailLimit());

            int detailClicks = 0;
            List<Future<?>> detailAiJobs = new ArrayList<>();
            try (ExecutorService detailAiPool = Executors.newFixedThreadPool(AI_PARALLELISM)) {
            for (CardPreview preview : worthClick) {
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    progressCallback.accept("用户取消投递", 0, 0);
                    return;
                }
                if (pageNeedsHuman()) {
                    waitForHuman("Boss 弹出人机验证或登录页。请到 Boss 拉起的 Chrome 处理。");
                }
                if (preview.encryptId == null || preview.encryptId.isBlank()) {
                    log.warn("卡片没有岗位ID，保持待读 | {} | {}", preview.company, preview.job);
                    continue;
                }
                Locator cardToClick = findCardScrolling(preview.encryptId);
                if (cardToClick == null) {
                    log.warn("找不到岗位ID对应卡片，保持待读 | {} | {} | {}",
                            preview.encryptId, preview.company, preview.job);
                    continue;
                }

                Response detailResp = null;
                try {
                    final Locator clickTarget = cardToClick;
                    detailResp = page.waitForResponse(
                            r -> {
                                try {
                                    return r.url() != null && r.url().contains("/wapi/zpgeek/job/detail.json")
                                            && "GET".equalsIgnoreCase(r.request().method());
                                } catch (Throwable ignore) {
                                    return false;
                                }
                            },
                            new Page.WaitForResponseOptions().setTimeout(15_000),
                            clickTarget::click);
                    detailClicks++;
                } catch (Throwable e) {
                    if (pageNeedsHuman()) {
                        waitForHuman("Boss 点详情时弹出验证。请到 Boss 拉起的 Chrome 处理。");
                    } else {
                        log.warn("等待岗位详情超时 | 公司：{} | 岗位：{}", preview.company, preview.job);
                    }
                    continue;
                }
                pauseBetweenJobs();

                // 统一从请求返回的 JSON 中获取数据并做过滤
                String jobName = null;
                String jobSalary = null;
                java.util.List<String> tags = new java.util.ArrayList<>();
                String jobDesc = null;
                String bossName = null;
                String bossActive = null;
                String bossCompany = null;
                String bossJobTitle = null;
                String locationName = null;

                if (detailResp != null) {
                    try {
                        String body = detailResp.text();
                        // 保存原始 JSON 便于调试
                        appendRawJson(body);
                        // 解析并入库（仅在点击卡片触发时执行）
                        processJobDetailJsonAndInsert(body);

                        // 从 JSON 构建用于投递与过滤的字段
                        org.json.JSONObject root = new org.json.JSONObject(body);
                        org.json.JSONObject zpData = root.optJSONObject("zpData");
                        org.json.JSONObject jobInfo = zpData != null ? zpData.optJSONObject("jobInfo") : null;
                        org.json.JSONObject brand = zpData != null ? zpData.optJSONObject("brandComInfo") : null;
                        org.json.JSONObject boss = zpData != null ? zpData.optJSONObject("bossInfo") : null;

                        if (jobInfo != null) {
                            jobName = jobInfo.optString("jobName", "");
                            jobSalary = jobInfo.optString("salaryDesc", "");
                            String city = jobInfo.optString("locationName", "");
                            String exp = jobInfo.optString("experienceName", "");
                            String deg = jobInfo.optString("degreeName", "");
                            if (!city.isEmpty()) tags.add(city);
                            if (!exp.isEmpty()) tags.add(exp);
                            if (!deg.isEmpty()) tags.add(deg);
                            jobDesc = jobInfo.optString("postDescription", "");
                            locationName = city;
                        }

                        if (boss != null) {
                            bossName = boss.optString("name", "");
                            bossActive = boss.optString("activeTimeDesc", "");
                            bossJobTitle = boss.optString("title", "");
                        }

                        if (brand != null) {
                            bossCompany = brand.optString("brandName", "");
                        }
                    } catch (Throwable e) {
                        log.debug("点击卡片后解析岗位详情用于过滤失败：{}", e.getMessage());
                    }
                }

                // 创建Job对象（全部基于 JSON 字段）
                Job job = new Job();
                job.setJobName(jobName != null ? jobName : "");
                job.setSalary(jobSalary != null ? jobSalary : "");
                job.setJobArea(String.join(", ", tags));
                job.setCompanyName(bossCompany != null ? bossCompany : "");
                job.setRecruiter(bossName != null ? bossName : "");
                job.setJobInfo(jobDesc != null ? jobDesc : "");
                Locator moreInfoBtn = page.locator("a.more-job-btn");
                if (moreInfoBtn.count() > 0) {
                    String href = moreInfoBtn.first().getAttribute("href");
                    if (href != null && href.startsWith("/job_detail/")) {
                        job.setHref("https://www.zhipin.com" + href);
                    }
                }

                boolean blankJob = (jobName == null || jobName.isBlank())
                        && (bossCompany == null || bossCompany.isBlank());
                if (blankJob) {
                    emptyDetailStreak++;
                    log.warn("岗位详情为空 ({}/2) | url={}", emptyDetailStreak, safeUrl());
                    if (emptyDetailStreak >= 2 || pageNeedsHuman()) {
                        waitForHuman("Boss 读不到岗位详情，多半是人机验证或页面卡住。请到 Boss 拉起的 Chrome 处理。");
                        emptyDetailStreak = 0;
                    }
                    continue;
                }
                emptyDetailStreak = 0;
                if (job.getCompanyName() == null || job.getCompanyName().isBlank()) {
                    job.setCompanyName(preview.company);
                }
                if (job.getJobName() == null || job.getJobName().isBlank()) {
                    job.setJobName(preview.job);
                }
                if (job.getHref() == null || job.getHref().isBlank()) {
                    job.setHref(preview.href);
                }
                String cityPage = classifyCity(
                        (locationName != null && !locationName.isBlank()) ? locationName : preview.area);
                if ("其它".equals(cityPage) && isSearchCity(classifyCity(preview.area))) {
                    cityPage = classifyCity(preview.area);
                }
                String hrText = (bossActive != null && !bossActive.isBlank())
                        ? bossActive.trim()
                        : nullToEmpty(preview.active);
                lastHrActive = hrText;
                if (!hrText.isBlank() && !isActiveWithin3Days(hrText)) {
                    writeJobStage(keyword, job, cityPage, "rule_drop",
                            ruleReasonLabel("HR未近3天活跃：" + hrText), hrText, true);
                    continue;
                }

                if (SCREEN_ONLY) {
                    progressCallback.accept("正在筛选：" + jobName, detailClicks, worthClick.size());
                    final String citySnap = cityPage;
                    final String titleSnap = bossJobTitle;
                    final String activeSnap = lastHrActive;
                    final Job jobSnap = job;
                    detailAiJobs.add(detailAiPool.submit(() ->
                            screenJob(keyword, jobSnap, citySnap, titleSnap, activeSnap)));
                } else {
                    progressCallback.accept("正在投递：" + jobName, detailClicks, worthClick.size());
                    resumeSubmission(keyword, job);
                }
                postCount++;

                if (pageNeedsHuman()) {
                    log.warn("【{}】遍历过程中需要人工：{}", keyword, safeUrl());
                    waitForHuman("Boss 弹出人机验证或登录页。请到 Boss 拉起的 Chrome 处理。");
                }
            }
            for (Future<?> fut : detailAiJobs) {
                try {
                    fut.get();
                } catch (Exception e) {
                    log.warn("详情AI并行等待失败: {}", e.getMessage());
                }
            }
            }
            log.info("【{}】岗位已处理完毕！点详情{}次，筛过{}", keyword, detailClicks, postCount);
            } catch (Exception e) {
                log.error("【{}】处理失败，跳过该关键词继续下一个：{}", keyword, e.getMessage(), e);
                if (progressCallback != null) {
                    progressCallback.accept("关键词[" + keyword + "]失败已跳过：" + e.getMessage(), 0, 0);
                }
            }
            if (ki < keywords.size() - 1) {
                waitKeywordGap();
            }
        }
    }

    /**
     * 解析岗位详情 JSON，记下 encryptId → userId。不再入库。
     */
    private void processJobDetailJsonAndInsert(String body) {
        if (body == null || body.isEmpty()) return;
        try {
            JSONObject root = new JSONObject(body);
            JSONObject zpData = root.optJSONObject("zpData");
            if (zpData == null) return;

            JSONObject jobInfo = zpData.optJSONObject("jobInfo");
            JSONObject bossInfo = zpData.optJSONObject("bossInfo");
            if (jobInfo == null) return;

            String encryptId = jobInfo.optString("encryptId", null);
            String encryptUserId = jobInfo.optString("encryptUserId", null);
            if (encryptUserId == null && bossInfo != null) {
                encryptUserId = bossInfo.optString("encryptUserId", null);
                if (encryptUserId == null) {
                    encryptUserId = bossInfo.optString("encryptBossId", null);
                }
            }
            if (encryptId != null && encryptUserId != null) {
                encryptIdToUserId.put(encryptId, encryptUserId);
            }
        } catch (Throwable e) {
            log.debug("解析岗位详情 JSON 失败：{}", e.getMessage());
        }
    }

    public String decodeSalary(String text) {
        Map<Character, Character> fontMap = new HashMap<>();
        fontMap.put('\uE8F0', '0');
        fontMap.put('\uE8F1', '1');
        fontMap.put('\uE8F2', '2');
        fontMap.put('\uE8F3', '3');
        fontMap.put('\uE8F4', '4');
        fontMap.put('\uE8F5', '5');
        fontMap.put('\uE8F6', '6');
        fontMap.put('\uE8F7', '7');
        fontMap.put('\uE8F8', '8');
        fontMap.put('\uE8F9', '9');
        StringBuilder result = new StringBuilder();
        for (char c : text.toCharArray()) {
            result.append(fontMap.getOrDefault(c, c));
        }
        return result.toString();
    }

    // 安全获取单个文本内容
    public String safeText(Locator root, String selector) {
        Locator node = root.locator(selector);
        try {
            if (node.count() > 0 && node.innerText() != null) {
                return node.innerText().trim();
            }
        } catch (Exception e) {
            // ignore
        }
        return "";
    }

    // 安全获取多个文本内容
    public List<String> safeAllText(Locator root, String selector) {
        try {
            return root.locator(selector).allInnerTexts();
        } catch (Exception e) {
            return new ArrayList<>();
        }
    }

    // Boss姓名+活跃状态拆分
    public String[] splitBossName(String raw) {
        String[] bossParts = raw.trim().split("\\s+");
        String bossName = bossParts[0];
        String bossActive = bossParts.length > 1 ? String.join(" ", Arrays.copyOfRange(bossParts, 1, bossParts.length)) : "";
        return new String[]{bossName, bossActive};
    }

    // Boss公司+职位拆分
    public String[] splitBossTitle(String raw) {
        String[] parts = raw.trim().split(" · ");
        String company = parts[0];
        String job = parts.length > 1 ? parts[1] : "";
        return new String[]{company, job};
    }

    // 匹配命中词条（用于日志输出过滤原因）
    private String findMatchedTerm(java.util.Collection<String> patterns, String text) {
        if (patterns == null || text == null) return null;
        try {
            for (String p : patterns) {
                if (p != null && !p.isEmpty() && text.contains(p)) {
                    return p;
                }
            }
        } catch (Exception ignore) {
        }
        return null;
    }

    public static String buildSearchUrl(BossConfig config, String cityCode) {
        String baseUrl = "https://www.zhipin.com/web/geek/jobs";
        if (config == null) {
            return baseUrl;
        }
        List<String> params = new ArrayList<>();
        addParam(params, JobUtils.appendParam("city", cityCode));
        addParam(params, JobUtils.appendParam("jobType", config.getJobType()));
        addParam(params, JobUtils.appendListParam("salary", config.getSalary()));
        addParam(params, JobUtils.appendListParam("experience", config.getExperience()));
        addParam(params, JobUtils.appendListParam("degree", config.getDegree()));
        addParam(params, JobUtils.appendListParam("scale", config.getScale()));
        addParam(params, JobUtils.appendListParam("industry", config.getIndustry()));
        addParam(params, JobUtils.appendListParam("stage", config.getStage()));
        if (params.isEmpty()) {
            return baseUrl;
        }
        return baseUrl + "?" + String.join("&", params);
    }

    private static void addParam(List<String> params, String param) {
        if (param == null || param.isEmpty()) {
            return;
        }
        params.add(param.startsWith("&") ? param.substring(1) : param);
    }

    private String getSearchUrl(String cityCode) {
        return buildSearchUrl(config, cityCode);
    }

    /**
     * 进入岗位列表页。
     * <p>
     * 优先模拟真人路径：回首页 -> 在搜索框里逐字输入关键词 -> 点搜索按钮，
     * 而不是冷启动直接把拼好的列表页 URL 丢给浏览器。
     * <p>
     * UI 搜索只能带上关键词和首页当前城市，config 里的城市/薪资/经验等筛选项仍然只能靠 URL，
     * 所以落地之后如果条件对不上，会再做一次同标签页跳转 —— 此时已经是热会话 + 同源 referer，
     * 和冷启动直闯不是一回事。UI 搜索任何一步失败都会退回原来的直接跳转，不影响主流程。
     */
    private void openJobList(String keyword, String targetUrl, String cityCode) {
        boolean uiSearchDone = USE_UI_SEARCH && searchFromHomePage(keyword);
        if (!uiSearchDone) {
            navigateToJobList(targetUrl);
        } else if (needsUrlFilters(targetUrl, cityCode)) {
            log.info("【{}】UI搜索已落地，补充筛选条件跳转：{}", keyword, targetUrl);
            navigateToJobList(targetUrl);
        }
        warnIfSecurityCheck(keyword);
    }

    /**
     * 在 Boss 首页搜索框里做一次真实的 UI 搜索。
     *
     * @return 是否成功落到岗位列表页
     */
    private boolean searchFromHomePage(String keyword) {
        try {
            String current = page.url();
            if (current == null || !current.startsWith(BOSS_HOME_URL) || current.contains("/web/geek/")) {
                navigateTo(BOSS_HOME_URL);
            }
            // 首页落地后还会自己跳一次（/shanghai/?seoRefer=index 之类），
            // 不等它跳完就找搜索框，会卡在 "waiting for navigation to finish" 直到超时
            waitForPageSettled();

            Locator input = page.locator(HOME_SEARCH_INPUT).first();
            input.waitFor(new Locator.WaitForOptions().setTimeout(10_000));
            input.click();
            input.fill("");
            // 逐字输入，模拟真人打字节奏；一次性 fill 在输入行为层面太干净了
            input.pressSequentially(keyword, new Locator.PressSequentiallyOptions().setDelay(140));
            PlaywrightUtil.sleep(1);

            Locator searchBtn = page.locator(HOME_SEARCH_BUTTON).first();
            if (searchBtn.count() > 0) {
                searchBtn.click();
            } else {
                input.press("Enter");
            }
            // 表单提交是当前标签页跳转；若 Boss 改成新开标签页，这里会超时并退回直接跳转
            page.waitForURL("**/web/geek/jobs**", new Page.WaitForURLOptions().setTimeout(15_000));
            log.info("【{}】已通过首页搜索框进入岗位列表：{}", keyword, page.url());
            return true;
        } catch (Exception e) {
            log.warn("【{}】首页UI搜索失败，退回直接跳转：{}", keyword, e.getMessage());
            return false;
        }
    }

    /**
     * UI 搜索落地后，判断还需不需要用 URL 把筛选条件补上。
     */
    private boolean needsUrlFilters(String targetUrl, String cityCode) {
        String landed = page.url();
        if (landed == null) {
            return true;
        }
        // 首页搜索用的是首页当前城市，不一定等于配置里的城市
        if (cityCode != null && !cityCode.isEmpty() && !landed.contains("city=" + cityCode)) {
            return true;
        }
        // 除 city/query 外还有别的筛选项（薪资、经验、学历……），UI 搜索带不上
        int queryStart = targetUrl.indexOf('?');
        if (queryStart < 0) {
            return false;
        }
        for (String param : targetUrl.substring(queryStart + 1).split("&")) {
            int eq = param.indexOf('=');
            String name = eq < 0 ? param : param.substring(0, eq);
            String value = eq < 0 ? "" : param.substring(eq + 1);
            if (value.isEmpty() || "city".equals(name) || "query".equals(name)) {
                continue;
            }
            return true;
        }
        return false;
    }

    private void navigateToJobList(String url) {
        navigateTo(url);
    }

    /**
     * 导航并重试一次。
     * <p>
     * Boss 页面自己会做客户端跳转，撞上时 Playwright 报 net::ERR_ABORTED；
     * 这类失败重试一次基本就过了，不该让整个投递任务因此中止。
     */
    private void navigateTo(String url) {
        // Boss 的 SPA 在网络不佳或被限流时，15 秒常常不够，之前实测连着两次都超时
        Page.NavigateOptions options = new Page.NavigateOptions()
                .setWaitUntil(com.microsoft.playwright.options.WaitUntilState.DOMCONTENTLOADED)
                .setTimeout(45_000);
        try {
            page.navigate(url, options);
        } catch (Exception first) {
            // 导航期间页面自己又跳了一次时，Playwright 会抛 "Object doesn't exist: request@/frame@"，
            // 但页面其实已经到位了。先看落地 URL，别白白重试一遍。
            if (landedOn(url)) {
                log.debug("导航报了失效对象异常但页面已到位，忽略：{}", first.getMessage());
                settleAfterNavigation();
                return;
            }
            log.warn("导航失败，1秒后重试一次：{} | {}", url, first.getMessage());
            PlaywrightUtil.sleep(1);
            try {
                page.navigate(url, options);
            } catch (Exception second) {
                if (!landedOn(url)) {
                    throw second;
                }
                log.debug("重试同样报失效对象异常但页面已到位，忽略：{}", second.getMessage());
            }
        }
        settleAfterNavigation();
    }

    /**
     * 判断页面是否已经落在目标地址上（只比较路径，查询参数会被 Boss 改写）。
     */
    private boolean landedOn(String targetUrl) {
        try {
            String current = page.url();
            if (current == null) {
                return false;
            }
            String targetPath = targetUrl.split("\\?")[0];
            return current.startsWith(targetPath);
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 等页面真正稳定下来再继续。
     * <p>
     * DOMCONTENTLOADED 返回之后 Boss 还会自己做客户端跳转，此时 frame 被替换，
     * 后续任何 locator 调用都会报 "Object doesn't exist: frame@..."。
     */
    private void settleAfterNavigation() {
        waitForPageSettled();
    }

    /**
     * 等页面进入 domcontentloaded，最多等 {@value #LOAD_STATE_TIMEOUT} 毫秒。
     * <p>
     * 两个坑都踩过了：
     * 一是不能等 LOAD/NETWORKIDLE —— Boss 是 SPA + WebSocket 长连接，这两个状态可能永远不到；
     * 二是必须显式给超时 —— 不给超时就是无限期挂起，而"卡住"不是异常，
     * 外面包 try/catch 完全没用（实测把线程挂了两分钟以上还在等）。
     */
    private void waitForPageSettled() {
        try {
            page.waitForLoadState(com.microsoft.playwright.options.LoadState.DOMCONTENTLOADED,
                    new Page.WaitForLoadStateOptions().setTimeout(LOAD_STATE_TIMEOUT));
        } catch (Exception ignore) {
            // 等不到就算了，后面的 locator 调用自己有超时
        }
        PlaywrightUtil.sleep(2);
    }

    /**
     * 判断是不是 Playwright 的"对象已失效"异常。
     * <p>
     * 页面频繁增删 frame 时，Playwright Java 在派发事件时会引用到已经销毁的对象，
     * 抛 "Object doesn't exist: frame@..."。这个异常和当时在飞的那个调用没有因果关系，
     * 连接本身仍然可用，重试即可。
     */
    private static boolean isStaleObjectError(Throwable e) {
        String message = e.getMessage();
        if (message == null) {
            return false;
        }
        // 两类都是"页面在动"导致的瞬时异常，跟调用本身没有因果关系，重试就好：
        // - Object doesn't exist: frame@/request@  事件派发时引用到已销毁的对象
        // - Execution context was destroyed         求值期间页面发生了导航
        return message.contains("Object doesn't exist")
                || message.contains("Execution context was destroyed");
    }

    /**
     * 进入岗位列表并等列表渲染出来，整段带重试。
     * Boss 首页/列表页在登录态下会连着跳好几次，一次失败很正常。
     */
    private void openJobListWithRetry(String keyword, String targetUrl, String cityCode) {
        // 只重试一次：每次都要走导航(最长45秒×2) + 等列表(15秒×3)，
        // 试三轮的话一个关键词失败要耗掉好几分钟，界面上看着就是"卡住不动"
        RuntimeException last = null;
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                openJobList(keyword, targetUrl, cityCode);
                waitForJobList();
                return;
            } catch (RuntimeException e) {
                last = e;
                log.warn("【{}】进入岗位列表失败（第{}/2次）：{}", keyword, attempt,
                        e.getMessage() == null ? e.toString() : e.getMessage().split("\n")[0]);
                if (attempt < 2) {
                    PlaywrightUtil.sleep(3);
                }
            }
        }
        throw last;
    }

    /**
     * 统计当前列表里的岗位卡片数量，对失效对象异常做重试。
     */
    private int countJobCards() {
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return page.locator(JOB_LIST_SELECTOR).count();
            } catch (Exception e) {
                if (!isStaleObjectError(e) || attempt == 3) {
                    if (isStaleObjectError(e)) {
                        log.warn("统计岗位数量始终失败，按 0 处理：{}", e.getMessage());
                        return 0;
                    }
                    throw e;
                }
                PlaywrightUtil.sleep(1);
            }
        }
        return 0;
    }

    /**
     * 等待岗位列表容器出现，带重试。
     * 页面在这期间可能还在跳转，一次失败不代表真的没有列表。
     */
    private void waitForJobList() {
        // Boss 改版频繁，推荐页和搜索结果页的容器类名不一样。
        // 用逗号把候选选择器拼成一个，让 Playwright 一次性等"任意一个先出现"，
        // 不要逐个 8 秒串行试 —— 那样一轮就要 48 秒，页面正常时也慢得像卡死。
        String containers = String.join(", ",
                "ul.rec-job-list",
                "ul.job-list-box",
                ".job-list-box",
                ".search-job-result",
                "li.job-card-box",
                "li.job-card-wrapper");

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                page.waitForSelector(containers,
                        new Page.WaitForSelectorOptions().setTimeout(15_000));
                log.info("岗位列表容器已出现（第{}次尝试）", attempt);
                return;
            } catch (Exception e) {
                log.warn("等待岗位列表失败（第{}/3次），当前页面: {}", attempt, safeUrl());
                settleAfterNavigation();
            }
        }
        dumpListPageStructure();
        throw new IllegalStateException("岗位列表始终未出现，当前页面: " + safeUrl());
    }

    private String safeUrl() {
        try {
            return page.url();
        } catch (Exception e) {
            return "(取不到URL)";
        }
    }

    /**
     * 列表容器一个都没命中时，把页面上的候选列表结构打出来，方便修选择器。
     */
    private void dumpListPageStructure() {
        try {
            Object info = page.evaluate("""
                    () => {
                      const uls = Array.from(document.querySelectorAll('ul,div'))
                        .filter(el => el.className && typeof el.className === 'string'
                                   && /job|list|rec/i.test(el.className))
                        .slice(0, 15)
                        .map(el => el.tagName.toLowerCase() + '.' + el.className.trim().replace(/\\s+/g, '.')
                                 + ' (children=' + el.childElementCount + ')');
                      return { title: document.title, url: location.href, candidates: uls };
                    }""");
            log.warn("列表页结构快照: {}", info);
        } catch (Exception e) {
            log.warn("抓取列表页结构失败: {}", e.getMessage());
        }
    }

    /**
     * 落地后检查是否被弹到风控/验证页，日志里能直接看出是哪一步触发的。
     */
    private void warnIfSecurityCheck(String keyword) {
        String url = page.url();
        if (url == null) {
            return;
        }
        if (isSecurityVerifyUrl(url) || pageNeedsHuman()) {
            log.warn("【{}】进入岗位列表时需要人工：{}", keyword, url);
            waitForHuman("Boss 进入列表前弹出验证或登录。请到 Boss 拉起的 Chrome 处理。");
        }
    }

    private String loadCandidateProfile() {
        if (candidateProfile != null) {
            return candidateProfile;
        }
        String text = localBossSettings.candidateProfile();
        candidateProfile = text == null || text.isBlank()
                ? "杭州/上海 Python / AI 实习。Agent、LLM 应用优先。城市只分页不淘汰。"
                : text.trim();
        return candidateProfile;
    }

    /**
     * 列表前置规则。岗位名字面（含前端/运营等）在这里；其余标题/JD 语义走 AI。城市只分页。
     * 列表卡片没有招聘者头衔，不在这里打头衔。
     */
    private String ruleDropReason(String jobName, String company, String bossActive) {
        if (bossActive != null && !bossActive.isBlank()
                && !isActiveWithin3Days(bossActive)) {
            return "HR未近3天活跃：" + bossActive.trim();
        }
        if (jobName != null && blackJobs != null && blackJobs.stream().anyMatch(jobName::contains)) {
            String term = findMatchedTerm(blackJobs, jobName);
            return "职位黑名单命中" + (term != null ? "：" + term : "");
        }
        if (company != null && blackCompanies != null && blackCompanies.stream().anyMatch(company::contains)) {
            String term = findMatchedTerm(blackCompanies, company);
            return "公司黑名单命中" + (term != null ? "：" + term : "");
        }
        String companyToken = firstTokenHit(company, localBossSettings.companyTokens());
        if (companyToken != null) {
            return "公司名含：" + companyToken;
        }
        String jobToken = firstTokenHit(jobName, localBossSettings.jobTitleTokens());
        if (jobToken != null) {
            return "岗位名含：" + jobToken;
        }
        return null;
    }

    private static String firstTokenHit(String text, java.util.List<String> tokens) {
        if (text == null || text.isBlank() || tokens == null) {
            return null;
        }
        for (String token : tokens) {
            if (token != null && !token.isEmpty() && containsJobToken(text, token)) {
                return token;
            }
        }
        return null;
    }

    /** 「训练」不匹配「后训练」。 */
    private static boolean containsJobToken(String text, String token) {
        if (!text.contains(token)) {
            return false;
        }
        if ("训练".equals(token)) {
            return text.replace("后训练", "").contains("训练");
        }
        return true;
    }

    private static boolean hasInactiveHrText(JSONObject row) {
        if (row == null) {
            return false;
        }
        String active = row.optString("active", "");
        return !active.isBlank() && !isActiveWithin3Days(active);
    }

    /** 已过列表但详情活跃不是近 3 天：改判到规则，下次可按卡片文案重开。 */
    private void reclassifyInactiveHrRows() {
        boolean changed = false;
        for (JSONObject row : screenRows.values()) {
            if (!hasInactiveHrText(row)) {
                continue;
            }
            String stage = row.optString("stage", "");
            if ("rule_drop".equals(stage) && row.optBoolean("hrDrop", false)) {
                continue;
            }
            String active = row.optString("active", "").trim();
            row.put("stage", "rule_drop");
            row.put("reason", ruleReasonLabel("HR未近3天活跃：" + active));
            row.put("hrDrop", true);
            changed = true;
        }
        if (!changed) {
            return;
        }
        skipTerminalKeys.clear();
        hrDropKeys.clear();
        pendingDetailKeys.clear();
        otherCityPendingKeys.clear();
        for (JSONObject row : screenRows.values()) {
            indexSkipState(row);
        }
        persistScreenRows();
    }

    /** Boss 文案：在线 / 刚刚活跃 / 今日活跃 / 3日内活跃。本周及更早不算。 */
    static boolean isActiveWithin3Days(String bossActive) {
        if (bossActive == null || bossActive.isBlank()) {
            return false;
        }
        String t = bossActive.trim();
        if (t.contains("未上线")) {
            return false;
        }
        return t.contains("在线")
                || t.contains("刚刚")
                || t.contains("今日")
                || t.contains("今天")
                || t.contains("3日内")
                || t.contains("2日内")
                || t.contains("1日内")
                || t.contains("3天内")
                || t.contains("2天内")
                || t.contains("1天内");
    }

    /** 列表接口文案优先于卡片 DOM，再退回已写入 jsonl 的活跃。 */
    private String effectiveActive(CardPreview preview, String listKey) {
        if (preview != null && preview.encryptId != null && !preview.encryptId.isBlank()) {
            String fromList = listJsonActive.get(preview.encryptId);
            if (fromList != null && !fromList.isBlank()) {
                return fromList.trim();
            }
        }
        if (preview != null && preview.active != null && !preview.active.isBlank()) {
            return preview.active.trim();
        }
        JSONObject row = screenRows.get(listKey);
        if (row != null) {
            String stored = row.optString("active", "");
            if (!stored.isBlank()) {
                return stored.trim();
            }
        }
        return "";
    }

    private String extractEncryptId(Job job) {
        return extractEncryptIdFromHref(job != null ? job.getHref() : null);
    }

    /** 列表卡片 a.job-name 的 href：/job_detail/{encryptId}.html?... */
    private String extractEncryptIdFromHref(String href) {
        if (href == null || href.isBlank()) {
            return null;
        }
        String key = "/job_detail/";
        int idx = href.indexOf(key);
        if (idx < 0) {
            return null;
        }
        int start = idx + key.length();
        int end = href.indexOf(".html", start);
        if (end < 0) {
            int q = href.indexOf('?', start);
            end = q >= 0 ? q : href.length();
        }
        String id = href.substring(start, end).trim();
        if (id.isEmpty() || !id.matches("[A-Za-z0-9_-]+")) {
            return null;
        }
        return id;
    }

    private static String jobKey(String company, String job) {
        return nullToEmpty(company) + "|" + nullToEmpty(job);
    }

    /** 有岗位 ID 用 id:，否则 name:公司|岗位。空串表示无法建键。 */
    private static String rowKey(String encryptId, String company, String job) {
        if (encryptId != null && !encryptId.isBlank()) {
            return "id:" + encryptId.trim();
        }
        String name = jobKey(company, job);
        if ("|".equals(name)) {
            return "";
        }
        return "name:" + name;
    }

    private static String previewKey(CardPreview preview) {
        return rowKey(preview.encryptId, preview.company, preview.job);
    }

    private static String rowKeyOf(JSONObject row) {
        if (row == null) {
            return "";
        }
        return rowKey(row.optString("encryptId", ""), row.optString("company"), row.optString("job"));
    }

    private static boolean isPlacedRow(JSONObject row) {
        if (row == null) {
            return false;
        }
        String stage = row.optString("stage", "").trim();
        String city = row.optString("cityPage", "").trim();
        return switch (stage) {
            case "rule_drop", "ai_title_drop", "ai_title_pending", "ai_jd_drop",
                 "jd_wait", "jd_wait_other", "ai_jd_pending", "ai_keep" ->
                    "杭州".equals(city) || "上海".equals(city) || "其它".equals(city);
            default -> false;
        };
    }

    /** 只认文案含「杭州」「上海」。区县、空值、外地都进其它。 */
    static String classifyCity(String area) {
        String t = area == null ? "" : area;
        if (t.contains("杭州")) {
            return "杭州";
        }
        if (t.contains("上海")) {
            return "上海";
        }
        return "其它";
    }

    private static boolean isSearchCity(String cityPage) {
        return "杭州".equals(cityPage) || "上海".equals(cityPage);
    }

    private void harvestVisibleCards(String keyword, Map<String, CardPreview> harvested) {
        try {
            Object raw = page.evaluate("""
                    () => {
                      const LINE = /^(在线|刚刚活跃|今日活跃|今天活跃|[1-3]日内活跃|[1-3]天内活跃|本周活跃|[0-9]+周内活跃|本月活跃|[0-9]+月内活跃|半年前活跃|近半年活跃|未上线)$/;
                      const activeOf = (el) => {
                        let onlineMark = false;
                        const nodes = el.querySelectorAll('span.boss-active-time, .boss-online-tag, .boss-online, .active-time, [class*="active-time"]');
                        for (const n of nodes) {
                          const t = ((n.innerText || n.textContent || '') + '').trim().replace(/\\s+/g, '');
                          if (t) return t;
                          const cls = (n.getAttribute && n.getAttribute('class')) || '';
                          if (cls.includes('online')) onlineMark = true;
                        }
                        const info = el.querySelector('.boss-info, .job-card-footer, .card-footer, .job-info-footer');
                        const roots = info ? [info, el] : [el];
                        for (const root of roots) {
                          const lines = ((root.innerText || '') + '').split(/\\n/).map(x => x.trim()).filter(Boolean);
                          for (let i = lines.length - 1; i >= 0; i--) {
                            const line = lines[i].replace(/\\s+/g, '');
                            if (LINE.test(line)) return line;
                          }
                        }
                        return onlineMark ? '在线' : '';
                      };
                      return Array.from(document.querySelectorAll('ul.rec-job-list li.job-card-box')).map(el => {
                        const a = el.querySelector('a.job-name');
                        const loc = el.querySelector('span.company-location');
                        const name = el.querySelector('span.boss-name');
                        return {
                          job: (a && a.innerText ? a.innerText : '').trim(),
                          company: (name && name.innerText ? name.innerText : '').trim(),
                          area: (loc && loc.innerText ? loc.innerText : '').trim(),
                          active: activeOf(el),
                          href: (a && a.getAttribute('href')) ? a.getAttribute('href') : ''
                        };
                      });
                    }
                    """);
            if (!(raw instanceof List<?> rows)) {
                return;
            }
            for (Object rowObj : rows) {
                if (!(rowObj instanceof Map<?, ?> m)) {
                    continue;
                }
                String job = mapStr(m, "job");
                String company = mapStr(m, "company");
                String area = mapStr(m, "area");
                String active = mapStr(m, "active");
                String href = mapStr(m, "href");
                String encryptId = extractEncryptIdFromHref(href);
                if (encryptId != null && !encryptId.isBlank() && (active == null || active.isBlank())) {
                    String fromList = listJsonActive.get(encryptId);
                    if (fromList != null && !fromList.isBlank()) {
                        active = fromList;
                    }
                }
                if (job.isEmpty() && company.isEmpty() && (encryptId == null || encryptId.isBlank())) {
                    continue;
                }
                String key = rowKey(encryptId, company, job);
                if (key.isEmpty()) {
                    continue;
                }
                CardPreview next = new CardPreview(job, company, area, active, href, encryptId == null ? "" : encryptId);
                CardPreview existing = harvested.get(key);
                if (existing != null) {
                    if ("其它".equals(classifyCity(existing.area)) && isSearchCity(classifyCity(area))) {
                        harvested.put(key, next);
                    }
                    continue;
                }
                harvested.put(key, next);
            }
        } catch (Exception e) {
            log.debug("收取列表卡片失败: {}", e.getMessage());
        }
    }

    private String cardHref(Locator card) {
        try {
            Locator a = card.locator("a.job-name");
            if (a.count() == 0) {
                return "";
            }
            String href = a.first().getAttribute("href");
            if (href == null || href.isBlank()) {
                return "";
            }
            if (href.startsWith("/")) {
                return "https://www.zhipin.com" + href;
            }
            return href;
        } catch (Exception e) {
            return "";
        }
    }

    private void writePreviewStage(String keyword, CardPreview preview, String stage,
                                   String reason, boolean hrDrop) {
        lastHrActive = preview.active;
        JSONObject patch = new JSONObject();
        patch.put("keyword", keyword);
        patch.put("company", nullToEmpty(preview.company));
        patch.put("job", nullToEmpty(preview.job));
        patch.put("area", nullToEmpty(preview.area));
        patch.put("active", nullToEmpty(preview.active));
        patch.put("href", nullToEmpty(preview.href));
        patch.put("encryptId", nullToEmpty(preview.encryptId));
        patch.put("cityPage", classifyCity(preview.area));
        patch.put("stage", stage);
        patch.put("reason", requireReason(reason));
        patch.put("hrDrop", hrDrop);
        patch.put("hasJd", false);
        upsertScreenRow(patch);
        log.info("{} | {} | {} | {}", stage, preview.company, preview.job, patch.getString("reason"));
    }

    private void writeJobStage(String keyword, Job job, String cityPage, String stage,
                               String reason, String hrActive) {
        writeJobStage(keyword, job, cityPage, stage, reason, hrActive, false);
    }

    private void writeJobStage(String keyword, Job job, String cityPage, String stage,
                               String reason, String hrActive, boolean hrDrop) {
        JSONObject patch = new JSONObject();
        patch.put("keyword", keyword);
        patch.put("company", nullToEmpty(job.getCompanyName()));
        patch.put("job", nullToEmpty(job.getJobName()));
        patch.put("salary", nullToEmpty(job.getSalary()));
        patch.put("area", nullToEmpty(job.getJobArea()));
        patch.put("recruiter", nullToEmpty(job.getRecruiter()));
        patch.put("active", nullToEmpty(hrActive));
        patch.put("href", nullToEmpty(job.getHref()));
        patch.put("encryptId", nullToEmpty(extractEncryptIdFromHref(job.getHref())));
        patch.put("jd", nullToEmpty(job.getJobInfo()));
        patch.put("cityPage", cityPage == null ? classifyCity(job.getJobArea()) : cityPage);
        patch.put("stage", stage);
        patch.put("reason", requireReason(reason));
        patch.put("hrDrop", hrDrop);
        patch.put("hasJd", job.getJobInfo() != null && !job.getJobInfo().isBlank());
        upsertScreenRow(patch);
    }

    private void upsertScreenRow(JSONObject patch) {
        synchronized (screenRows) {
            upsertScreenRowLocked(patch);
        }
    }

    private void upsertScreenRowLocked(JSONObject patch) {
        String key = rowKeyOf(patch);
        if (key.isEmpty()) {
            return;
        }
        JSONObject row = screenRows.get(key);
        if (row == null && key.startsWith("id:")) {
            String nameKey = rowKey(null, patch.optString("company"), patch.optString("job"));
            if (!nameKey.isEmpty()) {
                row = screenRows.remove(nameKey);
            }
        }
        if (row == null) {
            row = new JSONObject();
        }
        for (String k : patch.keySet()) {
            row.put(k, patch.get(k));
        }
        stripDeadKeys(row);
        org.json.JSONArray arr = row.optJSONArray("keywords");
        if (arr == null) {
            arr = new org.json.JSONArray();
            row.put("keywords", arr);
        }
        String kw = patch.optString("keyword", "");
        if (!kw.isBlank()) {
            boolean found = false;
            for (int i = 0; i < arr.length(); i++) {
                if (kw.equals(arr.optString(i))) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                arr.put(kw);
            }
        }
        screenRows.put(key, row);
        persistScreenRows();
        indexSkipState(row);
    }

    private static void stripDeadKeys(JSONObject row) {
        row.remove("column");
        row.remove("status");
        row.remove("keep");
    }

    private void persistScreenRows() {
        StringBuilder sb = new StringBuilder();
        for (JSONObject row : screenRows.values()) {
            stripDeadKeys(row);
            sb.append(row).append(System.lineSeparator());
        }
        try {
            Files.writeString(screenLog(), sb.toString(), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        } catch (Exception e) {
            log.warn("写入筛选结果失败：{}", e.getMessage());
        }
    }

    private void indexSkipState(JSONObject row) {
        String key = rowKeyOf(row);
        if (key.isEmpty()) {
            return;
        }
        skipTerminalKeys.remove(key);
        hrDropKeys.remove(key);
        pendingDetailKeys.remove(key);
        otherCityPendingKeys.remove(key);
        String stage = row.optString("stage", "");
        switch (stage) {
            case "rule_drop" -> {
                if (row.optBoolean("hrDrop", false)) {
                    hrDropKeys.add(key);
                } else {
                    skipTerminalKeys.add(key);
                }
            }
            case "ai_title_drop", "ai_title_pending", "ai_jd_drop", "ai_keep", "ai_jd_pending" -> {
                if (hasInactiveHrText(row)) {
                    hrDropKeys.add(key);
                } else {
                    skipTerminalKeys.add(key);
                }
            }
            case "jd_wait" -> pendingDetailKeys.add(key);
            case "jd_wait_other" -> otherCityPendingKeys.add(key);
            default -> {
            }
        }
    }

    private Path screenLog() {
        return localBossSettings.screenResultsPath();
    }

    /** 本批不持久化：开始筛选覆盖指定 jsonl，不归档、不读历史文件。 */
    private void beginFreshRun() {
        screenRows.clear();
        skipTerminalKeys.clear();
        hrDropKeys.clear();
        pendingDetailKeys.clear();
        otherCityPendingKeys.clear();
        listJsonActive.clear();
        detailClicksReserved = 0;
        Path file = screenLog();
        try {
            Path parent = file.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(file, "", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            log.info("本轮筛选写入 {}（覆盖，不归档）", file.toAbsolutePath());
        } catch (Exception e) {
            throw new IllegalStateException("无法写入 " + file + ": " + e.getMessage(), e);
        }
    }

    private void loadScreenState() {
        screenRows.clear();
        skipTerminalKeys.clear();
        hrDropKeys.clear();
        pendingDetailKeys.clear();
        otherCityPendingKeys.clear();
        Path file = screenLog();
        if (!Files.exists(file)) {
            return;
        }
        try {
            List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
            for (String line : lines) {
                if (line == null || line.isBlank()) {
                    continue;
                }
                try {
                    JSONObject row = new JSONObject(line);
                    if (!isPlacedRow(row)) {
                        continue;
                    }
                    String key = rowKeyOf(row);
                    if (key.isEmpty()) {
                        continue;
                    }
                    stripDeadKeys(row);
                    screenRows.put(key, row);
                    indexSkipState(row);
                } catch (Exception ignore) {
                }
            }
            reclassifyInactiveHrRows();
            log.info("已加载筛选 {} 条（终局跳过{}，HR可重开{}，待读{}，其它城市{}）",
                    screenRows.size(), skipTerminalKeys.size(), hrDropKeys.size(),
                    pendingDetailKeys.size(), otherCityPendingKeys.size());
        } catch (Exception e) {
            log.warn("读取筛选结果失败：{}", e.getMessage());
        }
    }

    private void screenJob(String keyword, Job job, String cityPage, String recruiterTitle, String hrActive) {
        String raw;
        try {
            raw = aiService.sendRequest(buildScreenPrompt(keyword, job, recruiterTitle, hrActive, cityPage));
        } catch (Exception e) {
            log.warn("AI筛选失败，记为待人工 | 公司：{} | 岗位：{} | {}", job.getCompanyName(), job.getJobName(), e.getMessage());
            writeJobStage(keyword, job, cityPage, "ai_jd_pending",
                    aiJdFailReason(e.getMessage()), hrActive);
            return;
        }
        Boolean keep = parseKeepOrNull(raw);
        String reason = parseReason(raw);
        if (keep == null) {
            writeJobStage(keyword, job, cityPage, "ai_jd_pending",
                    aiJdFailReason(reason), hrActive);
            return;
        }
        String stage = keep ? "ai_keep" : "ai_jd_drop";
        String labeled = aiJdReasonLabel(reason);
        log.info("{} | 公司：{} | 岗位：{} | {}", stage, job.getCompanyName(), job.getJobName(), labeled);
        writeJobStage(keyword, job, cityPage, stage, labeled, hrActive);
        if (keep) {
            synchronized (resultList) {
                resultList.add(job);
            }
        }
    }

    private String buildScreenPrompt(String keyword, Job job, String recruiterTitle, String hrActive, String cityPage) {
        return localBossSettings.fill(localBossSettings.jdPrompt(), java.util.Map.of(
                "profile", loadCandidateProfile(),
                "keyword", nullToEmpty(keyword),
                "company", nullToEmpty(job.getCompanyName()),
                "job", nullToEmpty(job.getJobName()),
                "recruiterTitle", nullToEmpty(recruiterTitle),
                "hrActive", nullToEmpty(hrActive),
                "cityPage", nullToEmpty(cityPage),
                "salary", nullToEmpty(job.getSalary()),
                "area", nullToEmpty(job.getJobArea()),
                "jd", nullToEmpty(job.getJobInfo())
        ));
    }

    private static String nullToEmpty(String s) {
        return s == null ? "" : s;
    }

    private static String mapStr(Map<?, ?> m, String key) {
        Object v = m.get(key);
        if (v == null) {
            return "";
        }
        String s = String.valueOf(v).trim();
        return "null".equals(s) ? "" : s;
    }

    private Boolean parseKeepOrNull(String raw) {
        if (raw == null) {
            return null;
        }
        String json = extractJsonObject(raw);
        try {
            JSONObject o = new JSONObject(json);
            if (!o.has("keep")) {
                return null;
            }
            return o.getBoolean("keep");
        } catch (Exception ignore) {
            String lower = raw.toLowerCase(Locale.ROOT);
            if (lower.contains("\"keep\":true") || lower.contains("\"keep\": true")) {
                return true;
            }
            if (lower.contains("\"keep\":false") || lower.contains("\"keep\": false")) {
                return false;
            }
            return null;
        }
    }

    private static String requireReason(String reason) {
        String r = reason == null ? "" : reason.trim();
        return r.isEmpty() ? "未写明" : r;
    }

    private String carryReason(String listKey, String fallback) {
        JSONObject row = screenRows.get(listKey);
        if (row != null) {
            String prev = row.optString("reason", "").trim();
            if (!prev.isEmpty()) {
                if (fallback == null || fallback.isBlank() || prev.contains(fallback)) {
                    return prev;
                }
                return prev + "；" + fallback;
            }
        }
        return fallback;
    }

    private static String stripReasonBody(String raw) {
        if (raw == null) {
            return "";
        }
        return raw.trim().replaceFirst("^(规则|AI 标题|AI JD)\\s+", "").trim();
    }

    private static String ruleReasonLabel(String rule) {
        String body = stripReasonBody(rule);
        return "规则 " + (body.isEmpty() ? "未写明" : body);
    }

    private static String aiTitleReasonLabel(String reason) {
        String body = stripReasonBody(reason);
        return "AI 标题 " + (body.isEmpty() ? "无理由" : body);
    }

    private static String aiTitleFailReason(String reason) {
        return aiFailReason("标题", reason);
    }

    private static String aiJdReasonLabel(String reason) {
        String body = stripReasonBody(reason);
        return "AI JD " + (body.isEmpty() ? "无理由" : body);
    }

    private static String aiJdFailReason(String reason) {
        return aiFailReason("JD", reason);
    }

    private static String aiFailReason(String phase, String reason) {
        String r = reason == null ? "" : reason.replace('\n', ' ').trim();
        if (r.isEmpty()) {
            return "AI " + phase + " 失败或无法解析";
        }
        String body = stripReasonBody(r);
        String rest = body.isEmpty() ? r : body;
        if (r.contains("状态码") || r.startsWith("AI请求") || r.contains("upstream") || r.contains("auth_unavailable")) {
            return "AI " + phase + " 失败：" + shortenReason(rest, 80);
        }
        return "AI " + phase + " 无法解析：" + shortenReason(rest, 80);
    }

    private static String shortenReason(String text, int max) {
        if (text.length() <= max) {
            return text;
        }
        return text.substring(0, max);
    }

    private String parseReason(String raw) {
        if (raw == null) {
            return "空回复";
        }
        try {
            return new JSONObject(extractJsonObject(raw)).optString("reason", raw.trim());
        } catch (Exception ignore) {
            String t = raw.replace('\n', ' ').trim();
            return t.length() > 80 ? t.substring(0, 80) : t;
        }
    }

    private String extractJsonObject(String raw) {
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        if (start >= 0 && end > start) {
            return raw.substring(start, end + 1);
        }
        return raw;
    }

    /**
     * 备注：目前Boss无法通过新标签页打开立即沟通按钮，所以只能点击更多详情，然后从更多详情里打开聊天按钮
     */
    @SneakyThrows
    private void resumeSubmission(String keyword, Job job) {
        // 若收到停止指令，直接短路返回
        if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
            log.info("停止指令已触发，跳过投递 | 公司：{} | 岗位：{}", job.getCompanyName(), job.getJobName());
            return;
        }
        // 调试模式：仅遍历不投递
        if (Boolean.TRUE.equals(config.getDebugger())) {
            log.info("调试模式：仅遍历岗位，不投递 | 公司：{} | 岗位：{}", job.getCompanyName(), job.getJobName());
            return;
        }

        // 1. 查找"查看更多信息"按钮（必须存在且新开页）
        Locator moreInfoBtn = page.locator("a.more-job-btn");
        if (moreInfoBtn.count() == 0) {
            log.warn("未找到\"查看更多信息\"按钮，跳过...");
            return;
        }
        // 强制用js新开tab
        String href = moreInfoBtn.first().getAttribute("href");
        if (href == null || !href.startsWith("/job_detail/")) {
            log.warn("未获取到岗位详情链接，跳过...");
            return;
        }
        String detailUrl = "https://www.zhipin.com" + href;
        // 2. 在新窗口打开详情页
        Page detailPage = page.context().newPage();
        detailPage.navigate(detailUrl);
        PlaywrightUtil.sleep(1);

        // 3. 查找"立即沟通"按钮
        Locator chatBtn = detailPage.locator("a.btn-startchat, a.op-btn-chat");
        boolean foundChatBtn = false;
        for (int i = 0; i < 5; i++) {
            if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                log.info("停止指令已触发，结束查找聊天按钮 | 公司：{} | 岗位：{}", job.getCompanyName(), job.getJobName());
                try { detailPage.close(); } catch (Exception ignore) {}
                return;
            }
            if (chatBtn.count() > 0 && (chatBtn.first().textContent().contains("立即沟通"))) {
                foundChatBtn = true;
                break;
            }
            PlaywrightUtil.sleep(1);
        }
        if (!foundChatBtn) {
            log.warn("未找到立即沟通按钮，跳过岗位: {}", job.getJobName());
            // 关闭详情页
            try {
                detailPage.close();
            } catch (Exception ignore) {
            }
            return;
        }
        chatBtn.first().click();
        PlaywrightUtil.sleep(1);

        // 4. 等待聊天输入框
        Locator inputLocator = detailPage.locator("div#chat-input.chat-input[contenteditable='true'], textarea.input-area");
        boolean inputReady = false;
        for (int i = 0; i < 10; i++) {
            if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                log.info("停止指令已触发，结束等待聊天输入框 | 公司：{} | 岗位：{}", job.getCompanyName(), job.getJobName());
                try { detailPage.close(); } catch (Exception ignore) {}
                return;
            }
            if (inputLocator.count() > 0 && inputLocator.first().isVisible()) {
                inputReady = true;
                break;
            }
            PlaywrightUtil.sleep(1);
        }
        if (!inputReady) {
            log.warn("聊天输入框未出现，跳过: {}", job.getJobName());
            // 关闭详情页
            try {
                detailPage.close();
            } catch (Exception ignore) {
            }
            return;
        }

        // 5. AI智能生成打招呼语
        String aiMessage = null;
        if (config.getEnableAI()) {
            String jd = job.getJobInfo();
            if (jd != null && !jd.isEmpty()) {
                aiMessage = generateAiMessage(keyword, job.getJobName(), jd);
            }
        }
        String message = isValidString(aiMessage) ? aiMessage : config.getSayHi();

        // 6. 输入打招呼语
        Locator input = inputLocator.first();
        input.click();
        Object tagObj = input.evaluate("el => el.tagName.toLowerCase()");
        if (tagObj instanceof String && ((String) tagObj).equals("textarea")) {
            input.fill(message);
        } else {
            // 对 contenteditable 节点写入文本并派发 input 事件
            input.evaluate("(el, msg) => { el.innerText = msg; el.dispatchEvent(new Event('input')); }", message);
        }

        // 7. 点击发送按钮（div.send-message 或 button.btn-send）
        Locator sendText = detailPage.locator("div.send-message, button[type='send'].btn-send, button.btn-send");
        boolean sendSuccess = false;
        if (sendText.count() > 0) {
            sendText.first().click();
            PlaywrightUtil.sleep(1);
            sendSuccess = true;
            try {
                detailPage.locator("i.icon-close").first().click();
            } catch (Exception e) {
                log.error("发送文本小窗口关闭失败！");
            }
        } else {
            log.warn("未找到发送按钮，自动跳过！岗位：{}", job.getJobName());
        }

        // 8. 发送图片简历（可选）
        boolean imgResume = false;
        if (Boolean.TRUE.equals(config.getSendImgResume())) {
            imgResume = sendImageResume(detailPage);
        }

        log.info("代聊完成 | 公司：{} | 岗位：{} | 招呼语：{} | 图片简历：{}", job.getCompanyName(), job.getJobName(), message, imgResume ? "已发送" : "未发送");

        // 9. 关闭新打开的详情页
        try {
            detailPage.close();
        } catch (Exception ignore) {
        }
        PlaywrightUtil.sleep(1);

        // 10. 更新数据库投递状态 & 成功投递加入结果
        if (sendSuccess) {
            String encryptId = extractEncryptId(detailUrl);
            if (encryptId != null) {
                localBossSettings.recordOpened(encryptId, job.getCompanyName(), job.getJobName());
            }
            resultList.add(job);
        }
    }

    /**
     * 对当场点名的 encryptId 点立即沟通并发送招呼语。已开聊的跳过。
     */
    public int chatNamedJobs(List<String> encryptIds, boolean sendImage) {
        if (encryptIds == null || encryptIds.isEmpty()) {
            return 0;
        }
        String greeting = localBossSettings.loadGreeting();
        java.util.Set<String> opened = localBossSettings.openedEncryptIds();
        int ok = 0;
        for (int i = 0; i < encryptIds.size(); i++) {
            if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                break;
            }
            String encryptId = encryptIds.get(i);
            if (encryptId == null || encryptId.isBlank()) {
                continue;
            }
            encryptId = encryptId.trim();
            if (opened.contains(encryptId)) {
                log.info("已开聊，跳过 {}", encryptId);
                if (progressCallback != null) {
                    progressCallback.accept("已开聊，跳过 " + encryptId, i + 1, encryptIds.size());
                }
                continue;
            }
            if (progressCallback != null) {
                progressCallback.accept("代聊 " + encryptId, i + 1, encryptIds.size());
            }
            if (chatOneByEncryptId(encryptId, greeting, sendImage)) {
                opened.add(encryptId);
                ok++;
            }
        }
        return ok;
    }

    private boolean chatOneByEncryptId(String encryptId, String greeting, boolean sendImage) {
        String detailUrl = "https://www.zhipin.com/job_detail/" + encryptId + ".html";
        Page detailPage = page.context().newPage();
        try {
            detailPage.navigate(detailUrl);
            PlaywrightUtil.sleep(1);
            if (pageNeedsHuman()) {
                waitForHuman("Boss 弹出人机验证或登录页。请到 Boss 拉起的 Chrome 处理。");
            }
            Locator chatBtn = detailPage.locator("a.btn-startchat, a.op-btn-chat");
            boolean foundChatBtn = false;
            for (int i = 0; i < 5; i++) {
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    return false;
                }
                if (chatBtn.count() > 0) {
                    String text = chatBtn.first().textContent();
                    if (text != null && (text.contains("立即沟通") || text.contains("继续沟通"))) {
                        foundChatBtn = true;
                        break;
                    }
                }
                PlaywrightUtil.sleep(1);
            }
            if (!foundChatBtn) {
                log.warn("未找到立即沟通按钮，跳过 {}", encryptId);
                return false;
            }
            chatBtn.first().click();
            PlaywrightUtil.sleep(1);

            Locator inputLocator = detailPage.locator("div#chat-input.chat-input[contenteditable='true'], textarea.input-area");
            boolean inputReady = false;
            for (int i = 0; i < 10; i++) {
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    return false;
                }
                if (inputLocator.count() > 0 && inputLocator.first().isVisible()) {
                    inputReady = true;
                    break;
                }
                PlaywrightUtil.sleep(1);
            }
            if (!inputReady) {
                log.warn("聊天输入框未出现，跳过 {}", encryptId);
                return false;
            }

            Locator input = inputLocator.first();
            input.click();
            Object tagObj = input.evaluate("el => el.tagName.toLowerCase()");
            if (tagObj instanceof String && ((String) tagObj).equals("textarea")) {
                input.fill(greeting);
            } else {
                input.evaluate("(el, msg) => { el.innerText = msg; el.dispatchEvent(new Event('input')); }", greeting);
            }

            Locator sendText = detailPage.locator("div.send-message, button[type='send'].btn-send, button.btn-send");
            if (sendText.count() == 0) {
                log.warn("未找到发送按钮，跳过 {}", encryptId);
                return false;
            }
            sendText.first().click();
            PlaywrightUtil.sleep(1);
            try {
                detailPage.locator("i.icon-close").first().click();
            } catch (Exception ignore) {
            }

            if (sendImage) {
                sendImageResume(detailPage);
            }
            localBossSettings.recordOpened(encryptId, "", "");
            log.info("已开聊 {} 招呼已发", encryptId);
            return true;
        } catch (Exception e) {
            log.warn("代聊失败 {}: {}", encryptId, e.getMessage());
            return false;
        } finally {
            try {
                detailPage.close();
            } catch (Exception ignore) {
            }
        }
    }

    

    /** 滚列表时 Boss 自己打的 joblist，只听不请求。 */
    private void hookListJsonOnce() {
        if (listJsonHooked || page == null) {
            return;
        }
        listJsonHooked = true;
        page.onResponse(resp -> {
            try {
                String url = resp.url();
                if (url == null || !url.contains("/wapi/zpgeek/") || !url.contains("joblist")) {
                    return;
                }
                String body;
                try {
                    body = resp.text();
                } catch (Throwable ignore) {
                    return;
                }
                if (body == null || body.isBlank()) {
                    return;
                }
                ingestJobListActive(body);
            } catch (Throwable e) {
                log.debug("听列表接口失败：{}", e.getMessage());
            }
        });
    }

    private void ingestJobListActive(String body) {
        JSONObject root;
        try {
            root = new JSONObject(body);
        } catch (Exception e) {
            return;
        }
        JSONObject zpData = root.optJSONObject("zpData");
        org.json.JSONArray list = null;
        if (zpData != null) {
            list = zpData.optJSONArray("jobList");
            if (list == null) {
                list = zpData.optJSONArray("list");
            }
        }
        if (list == null) {
            list = root.optJSONArray("jobList");
        }
        if (list == null) {
            return;
        }
        for (int i = 0; i < list.length(); i++) {
            JSONObject job = list.optJSONObject(i);
            if (job == null) {
                continue;
            }
            JSONObject jobInfo = job.optJSONObject("jobInfo");
            JSONObject bossInfo = job.optJSONObject("bossInfo");
            String encryptId = job.optString("encryptId", "");
            if (encryptId.isBlank() && jobInfo != null) {
                encryptId = jobInfo.optString("encryptId", "");
            }
            if (encryptId.isBlank()) {
                encryptId = job.optString("encryptJobId", "");
            }
            String active = job.optString("activeTimeDesc", "");
            if (active.isBlank() && bossInfo != null) {
                active = bossInfo.optString("activeTimeDesc", "");
            }
            if (active.isBlank()) {
                active = job.optString("bossOnline", "").isBlank()
                        ? job.optString("activeTime", "")
                        : job.optString("bossOnline", "");
            }
            if (!encryptId.isBlank() && !active.isBlank()) {
                listJsonActive.put(encryptId, active.trim());
            }
        }
    }

    /**
     * 注册页面响应监听：拦截 /wapi/zpgeek/job/detail.json 请求并解析写库
     */
    private void attachJobDetailResponseListener() {
        if (page == null) return;
        page.onResponse(resp -> {
            try {
                String url = resp.url();
                if (url == null) return;
                // 仅处理 Boss 岗位详情接口（GET）
                if (url.contains("/wapi/zpgeek/job/detail.json") &&
                        "GET".equalsIgnoreCase(resp.request().method())) {
                    String body = null;
                    try {
                        body = resp.text();
                    } catch (Throwable ignore) {
                        // 某些情况下可能拿不到文本，忽略
                    }
                    if (body == null || body.isEmpty()) return;

                    // 保存原始 JSON 到 target/job.txt
                    appendRawJson(body);

                    // 仅记录映射与原始 JSON；入库逻辑已移动到点击卡片时
                    JSONObject root = new JSONObject(body);
                    JSONObject zpData = root.optJSONObject("zpData");
                    if (zpData == null) return;
                    JSONObject jobInfo = zpData.optJSONObject("jobInfo");
                    if (jobInfo == null) return;
                    String encryptId = jobInfo.optString("encryptId", null);
                    String encryptUserId = jobInfo.optString("encryptUserId", null);
                    if (encryptId != null && encryptUserId != null) {
                        encryptIdToUserId.put(encryptId, encryptUserId);
                    }
                }
            } catch (Throwable e) {
                log.debug("监听岗位详情响应处理异常：{}", e.getMessage());
            }
        });
    }


    /**
     * 追加保存原始 JSON 到 target/job.txt
     */
    private void appendRawJson(String body) {
        try {
            java.io.File dir = new java.io.File("target");
            if (!dir.exists()) dir.mkdirs();
            java.io.File file = new java.io.File(dir, "job.txt");
            try (java.io.FileWriter fw = new java.io.FileWriter(file, true)) {
                fw.write(body);
                fw.write(System.lineSeparator());
                fw.write("\n");
            }
        } catch (Exception e) {
            log.debug("写入 target/job.txt 失败：{}", e.getMessage());
        }
    }

    /**
     * 从详情页 URL 中提取 encrypt_id
     */
    private String extractEncryptId(String detailUrl) {
        try {
            if (detailUrl == null) return null;
            String key = "/job_detail/";
            int idx = detailUrl.indexOf(key);
            if (idx < 0) return null;
            int start = idx + key.length();
            int end = detailUrl.indexOf(".html", start);
            if (end < 0) end = detailUrl.length();
            return detailUrl.substring(start, end);
        } catch (Exception e) {
            return null;
        }
    }

    public boolean isValidString(String str) {
        return str != null && !str.isEmpty();
    }

    private boolean sendImageResume(Page page) {
        try {
            // 0) 资源存在性校验，避免后续无效操作
            URL resourceUrlCheck = Boss.class.getResource("/resume.jpg");
            if (resourceUrlCheck == null) {
                log.error("资源文件 resume.jpg 不存在，跳过发送图片简历");
                return false;
            }

            // 进入聊天页
            if (!page.url().contains("/web/geek/chat")) {
                Locator chatBtn = page.locator("a.btn-startchat, a.op-btn-chat");
                if (chatBtn.count() == 0) {
                    log.warn("未找到【继续沟通/立即沟通】按钮，跳过发送图片简历");
                    return false;
                }
                chatBtn.first().click();
                page.waitForURL("**/web/geek/chat**", new Page.WaitForURLOptions().setTimeout(15_000));
            }

            // 1) 解析图片路径（在可能触发文件选择器前就准备好）
            java.nio.file.Path imagePath = resolveResumeImage();

            // 精准定位聊天工具栏内的图片输入，避免匹配到页面其他上传控件
            Locator imgContainer = page.locator("div.btn-sendimg[aria-label='发送图片'], div[aria-label='发送图片'].btn-sendimg");
            Locator imageInput = imgContainer.locator("input[type='file'][accept*='image']").first();
            if (imageInput.count() == 0) {
                // 若未渲染，尝试拦截系统文件选择器；若未出现则普通点击促使 input 出现
                if (imgContainer.count() > 0) {
                    boolean chooserHandled = false;
                    try {
                        com.microsoft.playwright.FileChooser chooser = page.waitForFileChooser(() -> {
                            imgContainer.first().click();
                        });
                        chooser.setFiles(imagePath);
                        chooserHandled = true;
                        log.info("通过 FileChooser 直接提交图片文件，避免系统窗口阻塞");
                    } catch (com.microsoft.playwright.PlaywrightException ignore) {
                        // 未弹出系统文件选择器，继续常规流程
                    }
                    if (!chooserHandled) {
                        PlaywrightUtil.sleep(1);
                        imageInput = imgContainer.locator("input[type='file'][accept*='image']").first();
                    }
                }
            }
            imageInput.waitFor(new Locator.WaitForOptions().setTimeout(10_000));

            // 上传图片
            imageInput.setInputFiles(imagePath);
            PlaywrightUtil.sleep(1);
            return true;
        } catch (Throwable e) {
            log.error("发送图片简历失败：{}", e.getMessage(), e);
            return false;
        }
    }

    private java.nio.file.Path resolveResumeImage() throws Exception {
        URL resourceUrl = Boss.class.getResource("/resume.jpg");
        if (resourceUrl == null) {
            throw new IllegalStateException("资源文件 /resume.jpg 未找到，请将图片放置到 src/main/resources 目录下");
        }
        if ("file".equalsIgnoreCase(resourceUrl.getProtocol())) {
            return java.nio.file.Paths.get(resourceUrl.toURI());
        }
        java.nio.file.Path temp = java.nio.file.Files.createTempFile("resume-", ".jpg");
        try (java.io.InputStream in = Boss.class.getResourceAsStream("/resume.jpg")) {
            if (in == null) {
                throw new IllegalStateException("无法从类路径读取 /resume.jpg 资源");
            }
            java.nio.file.Files.copy(in, temp, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
        return temp;
    }

    /**
     * 检查岗位薪资是否符合预期
     *
     * @return boolean
     * true 不符合预期
     * false 符合预期
     * 期望的最低薪资如果比岗位最高薪资还小，则不符合（薪资给的太少）
     * 期望的最高薪资如果比岗位最低薪资还小，则不符合(要求太高满足不了)
     */
    private boolean isSalaryNotExpected(String salary) {
        try {
            // 1. 如果没有期望薪资范围，直接返回 false，表示"薪资并非不符合预期"
            List<Integer> expectedSalary = config.getExpectedSalary();
            if (!hasExpectedSalary(expectedSalary)) {
                return false;
            }

            // 2. 清理薪资文本（比如去掉 "·15薪"）
            salary = removeYearBonusText(salary);

            // 3. 如果薪资格式不符合预期（如缺少 "K" / "k"），直接返回 true，表示"薪资不符合预期"
            if (!isSalaryInExpectedFormat(salary)) {
                return true;
            }

            // 4. 进一步清理薪资文本，比如去除 "K"、"k"、"·" 等
            salary = cleanSalaryText(salary);

            // 5. 判断是 "月薪" 还是 "日薪"
            String jobType = detectJobType(salary);
            salary = removeDayUnitIfNeeded(salary); // 如果是按天，则去除 "元/天"

            // 6. 解析薪资范围并检查是否超出预期
            Integer[] jobSalaryRange = parseSalaryRange(salary);
            return isSalaryOutOfRange(jobSalaryRange,
                    getMinimumSalary(expectedSalary),
                    getMaximumSalary(expectedSalary),
                    jobType);

        } catch (Exception e) {
            log.error("岗位薪资获取异常！薪资文本【{}】,异常信息【{}】", salary, e.getMessage(), e);
            // 出错时，您可根据业务需求决定返回 true 或 false
            // 这里假设出错时无法判断，视为不满足预期 => 返回 true
            return true;
        }
    }

    /**
     * 是否存在有效的期望薪资范围
     */
    private boolean hasExpectedSalary(List<Integer> expectedSalary) {
        return expectedSalary != null && !expectedSalary.isEmpty();
    }

    /**
     * 去掉年终奖信息，如 "·15薪"、"·13薪"。
     */
    private String removeYearBonusText(String salary) {
        if (salary.contains("薪")) {
            // 使用正则去除 "·任意数字薪"
            return salary.replaceAll("·\\d+薪", "");
        }
        return salary;
    }

    /**
     * 判断是否是按天计薪，如发现 "元/天" 则认为是日薪
     */
    private String detectJobType(String salary) {
        if (salary.contains("元/天")) {
            return "day";
        }
        return "mouth";
    }

    /**
     * 如果是日薪，则去除 "元/天"
     */
    private String removeDayUnitIfNeeded(String salary) {
        if (salary.contains("元/天")) {
            return salary.replaceAll("元/天", "");
        }
        return salary;
    }

    private Integer getMinimumSalary(List<Integer> expectedSalary) {
        return expectedSalary != null && !expectedSalary.isEmpty() ? expectedSalary.get(0) : null;
    }

    private Integer getMaximumSalary(List<Integer> expectedSalary) {
        return expectedSalary != null && expectedSalary.size() > 1 ? expectedSalary.get(1) : null;
    }

    private boolean isSalaryInExpectedFormat(String salaryText) {
        return salaryText.contains("K") || salaryText.contains("k") || salaryText.contains("元/天");
    }

    private String cleanSalaryText(String salaryText) {
        salaryText = salaryText.replace("K", "").replace("k", "");
        int dotIndex = salaryText.indexOf('·');
        if (dotIndex != -1) {
            salaryText = salaryText.substring(0, dotIndex);
        }
        return salaryText;
    }

    private boolean isSalaryOutOfRange(Integer[] jobSalary, Integer miniSalary, Integer maxSalary,
                                       String jobType) {
        if (jobSalary == null) {
            return true;
        }
        if (miniSalary == null) {
            return false;
        }
        if (Objects.equals("day", jobType)) {
            // 期望薪资转为平均每日的工资
            maxSalary = BigDecimal.valueOf(maxSalary).multiply(BigDecimal.valueOf(1000))
                    .divide(BigDecimal.valueOf(21.75), 0, RoundingMode.HALF_UP).intValue();
            miniSalary = BigDecimal.valueOf(miniSalary).multiply(BigDecimal.valueOf(1000))
                    .divide(BigDecimal.valueOf(21.75), 0, RoundingMode.HALF_UP).intValue();
        }
        // 如果职位薪资下限低于期望的最低薪资，返回不符合
        if (jobSalary[1] < miniSalary) {
            return true;
        }
        // 如果职位薪资上限高于期望的最高薪资，返回不符合
        return maxSalary != null && jobSalary[0] > maxSalary;
    }

    public boolean containsDeadStatus(String activeTimeText, List<String> deadStatus) {
        for (String status : deadStatus) {
            if (activeTimeText.contains(status)) {
                return true;// 一旦找到包含的值，立即返回 true
            }
        }
        return false;// 如果没有找到，返回 false
    }

    private String generateAiMessage(String keyword, String jobName, String jd) {
        return config.getSayHi();
    }

    private Integer[] parseSalaryRange(String salaryText) {
        try {
            return Arrays.stream(salaryText.split("-")).map(s -> s.replaceAll("[^0-9]", "")) // 去除非数字字符
                    .map(Integer::parseInt) // 转换为Integer
                    .toArray(Integer[]::new); // 转换为Integer数组
        } catch (Exception e) {
            log.error("薪资解析异常！{}", e.getMessage(), e);
        }
        return null;
    }

    /** wait_time 没配或配得不合法时用的秒数 */
    private static final int DEFAULT_WAIT_TIME_SECONDS = 18;

    /**
     * 取配置里的 wait_time（秒），非法值一律退回默认值。
     */
    private int resolveWaitTimeSeconds() {
        try {
            String raw = config == null ? null : config.getWaitTime();
            if (raw != null && !raw.isBlank()) {
                int parsed = Integer.parseInt(raw.trim());
                if (parsed > 0) {
                    if (parsed < DEFAULT_WAIT_TIME_SECONDS) {
                        log.warn("wait_time={}s 小于下限 {}s，已钳制", parsed, DEFAULT_WAIT_TIME_SECONDS);
                        return DEFAULT_WAIT_TIME_SECONDS;
                    }
                    return parsed;
                }
            }
        } catch (NumberFormatException ignored) {
            // 配置里塞了非数字，用默认值
        }
        return DEFAULT_WAIT_TIME_SECONDS;
    }

    /**
     * 每处理完一个岗位后的停顿。
     * <p>
     * 上一轮实测 7 分钟连刷 297 个岗位详情，直接把 Boss 风控触发了，
     * 后续关键词全部被弹到安全验证页。这里按 wait_time 降速：
     * 正常模式在 [wait_time/2, wait_time] 之间随机，避免固定节奏本身成为特征；
     * 调试模式固定用最大值 wait_time，方便观察。
     */
    private String cardText(Locator card, String selector) {
        try {
            Locator loc = card.locator(selector);
            if (loc.count() == 0) {
                return "";
            }
            String t = loc.first().innerText();
            return t == null ? "" : t.trim();
        } catch (Exception e) {
            return "";
        }
    }

    private record CardPreview(String job, String company, String area, String active, String href, String encryptId) {}

    private String cardActiveText(Locator card) {
        String a = cardText(card, HR_ACTIVE_TIME);
        if (!a.isEmpty()) {
            return a;
        }
        return cardText(card, ".boss-online-tag, span.boss-active-time, .boss-online");
    }

    /** 只按列表链接里的 encryptId 找卡，不用岗位名兜底。 */
    private Locator findCardByEncryptId(String encryptId) {
        if (encryptId == null || encryptId.isBlank() || !encryptId.matches("[A-Za-z0-9_-]+")) {
            return null;
        }
        try {
            Locator hit = page.locator("ul.rec-job-list li.job-card-box")
                    .filter(new Locator.FilterOptions().setHas(
                            page.locator("a[href*='/job_detail/" + encryptId + "']")));
            if (hit.count() > 0) {
                return hit.first();
            }
        } catch (Exception ignore) {
        }
        return null;
    }

    /** 列表可能虚拟化，找不到就从顶往下滚找。 */
    private Locator findCardScrolling(String encryptId) {
        Locator hit = findCardByEncryptId(encryptId);
        if (hit != null) {
            try {
                hit.scrollIntoViewIfNeeded();
            } catch (Exception ignore) {
            }
            return hit;
        }
        try {
            page.evaluate("window.scrollTo(0, 0);");
            PlaywrightUtil.sleep(1);
            for (int i = 0; i < 80; i++) {
                if (pageNeedsHuman()) {
                    waitForHuman("Boss 找卡片时弹出人机验证或登录。请到 Boss 拉起的 Chrome 处理。");
                }
                hit = findCardByEncryptId(encryptId);
                if (hit != null) {
                    try {
                        hit.scrollIntoViewIfNeeded();
                    } catch (Exception ignore) {
                    }
                    return hit;
                }
                page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 0.9))");
                PlaywrightUtil.sleep(1);
            }
        } catch (Exception e) {
            log.debug("滚找卡片失败: {}", e.getMessage());
        }
        return null;
    }

    private enum TitleAction {
        CLICK, PARK, DROP
    }

    private static final class AiOutcome {
        private final Boolean keep;
        private final TitleAction title;
        private final String reason;

        private AiOutcome(Boolean keep, String reason) {
            this.keep = keep;
            this.title = null;
            this.reason = reason == null ? "" : reason;
        }

        private AiOutcome(TitleAction title, String reason) {
            this.keep = title == TitleAction.DROP ? Boolean.FALSE
                    : title == null ? null : Boolean.TRUE;
            this.title = title;
            this.reason = reason == null ? "" : reason;
        }

        private static AiOutcome fail(String reason) {
            return new AiOutcome((Boolean) null, reason);
        }
    }

    private List<AiOutcome> runAiParallel(String label, int n,
                                            Supplier<List<Callable<AiOutcome>>> tasks) {
        if (n <= 0) {
            return List.of();
        }
        log.info("{} 并行 {} 张，池大小 {}", label, n, AI_PARALLELISM);
        List<AiOutcome> out = new ArrayList<>(Collections.nCopies(n, AiOutcome.fail(label + "未返回")));
        try (ExecutorService pool = Executors.newFixedThreadPool(AI_PARALLELISM)) {
            List<Future<AiOutcome>> futs = new ArrayList<>(n);
            for (Callable<AiOutcome> task : tasks.get()) {
                futs.add(pool.submit(task));
            }
            for (int i = 0; i < futs.size(); i++) {
                if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                    pool.shutdownNow();
                    break;
                }
                try {
                    AiOutcome got = futs.get(i).get();
                    out.set(i, got != null ? got : AiOutcome.fail(label + "空结果"));
                } catch (Exception e) {
                    out.set(i, AiOutcome.fail(e.getMessage()));
                }
            }
        }
        return out;
    }

    /**
     * 用卡片标题问 AI：click / park / drop。调用前规则已过。不在这里写 jsonl。
     */
    private AiOutcome listTriageByTitle(String keyword, CardPreview preview) {
        String prompt = localBossSettings.fill(localBossSettings.titlePrompt(), java.util.Map.of(
                "keyword", nullToEmpty(keyword),
                "company", nullToEmpty(preview.company),
                "job", nullToEmpty(preview.job)
        ));
        String raw;
        try {
            raw = aiService.sendRequest(prompt);
        } catch (Exception e) {
            log.warn("标题AI失败 | {} | {} | {}", preview.company, preview.job, e.getMessage());
            return AiOutcome.fail(e.getMessage());
        }
        TitleAction action = parseTitleAction(raw);
        String reason = parseReason(raw);
        if (action == null) {
            return AiOutcome.fail(reason);
        }
        log.info("标题AI {} | {} | {} | {}", action.name().toLowerCase(Locale.ROOT),
                preview.company, preview.job, reason);
        return new AiOutcome(action, reason);
    }

    private TitleAction parseTitleAction(String raw) {
        if (raw == null) {
            return null;
        }
        String json = extractJsonObject(raw);
        try {
            JSONObject o = new JSONObject(json);
            if (o.has("action")) {
                String action = o.optString("action", "").trim().toLowerCase(Locale.ROOT);
                return switch (action) {
                    case "click" -> TitleAction.CLICK;
                    case "park" -> TitleAction.PARK;
                    case "drop" -> TitleAction.DROP;
                    default -> null;
                };
            }
        } catch (Exception ignore) {
        }
        Boolean keep = parseKeepOrNull(raw);
        if (keep == null) {
            return null;
        }
        return keep ? TitleAction.CLICK : TitleAction.DROP;
    }

    private int resolveDetailLimit() {
        if (config != null && config.getDetailLimit() != null) {
            return Math.max(0, config.getDetailLimit());
        }
        return localBossSettings.detailLimit();
    }

    private int resolveKeywordGapSeconds() {
        if (config != null && config.getKeywordGapSeconds() != null) {
            return Math.max(0, config.getKeywordGapSeconds());
        }
        return localBossSettings.keywordGapSeconds();
    }

    private void waitKeywordGap() {
        int gap = resolveKeywordGapSeconds();
        if (progressCallback != null) {
            progressCallback.accept("词间冷却 " + gap + " 秒，降低风控", 0, 0);
        }
        log.info("词间冷却 {} 秒", gap);
        int left = gap;
        while (left > 0) {
            if (shouldStopCallback != null && Boolean.TRUE.equals(shouldStopCallback.get())) {
                return;
            }
            int step = Math.min(5, left);
            PlaywrightUtil.sleep(step);
            left -= step;
        }
    }

    private void pauseBetweenJobs() {
        int waitTime = resolveWaitTimeSeconds();
        int seconds;
        if (Boolean.TRUE.equals(config.getDebugger())) {
            seconds = waitTime;
        } else {
            int min = Math.max(1, waitTime / 2);
            seconds = min >= waitTime ? waitTime
                    : ThreadLocalRandom.current().nextInt(min, waitTime + 1);
        }
        log.debug("岗位间停顿 {} 秒（wait_time={}，debugger={}）", seconds, waitTime, config.getDebugger());
        PlaywrightUtil.sleep(seconds);
    }

    /**
     * 判断是不是 Boss 的安全验证页。
     * <p>
     * 实测密集遍历后会被弹到 /web/passport/zp/verify.html（极验滑块，页面上是
     * div.geetest_success_correct 那一套），而原来的判断只认 verify-slider，
     * 导致真正遇到验证时程序把关键词当失败跳过，人也不知道要去过验证。
     */
    private static boolean isSecurityVerifyUrl(String url) {
        if (url == null) {
            return false;
        }
        return url.contains("/web/user/safe/verify-slider")
                || url.contains("/web/passport/zp/verify")
                || url.contains("/web/passport/zp/security")
                || url.contains("security-check");
    }

    private boolean pageNeedsHuman() {
        String url = safeUrl();
        if (isSecurityVerifyUrl(url)) {
            return true;
        }
        if (url.contains("/web/user/") && url.contains("login")) {
            return true;
        }
        try {
            Locator geo = page.locator(".geetest_panel, .geetest_holder, iframe[src*='geetest']");
            int n = geo.count();
            for (int i = 0; i < n; i++) {
                try {
                    if (geo.nth(i).isVisible()) {
                        return true;
                    }
                } catch (Exception ignore) {
                }
            }
        } catch (Exception ignore) {
        }
        return false;
    }

    private void waitForHuman(String reason) {
        humanAttention.raise(reason);
        if (progressCallback != null) {
            progressCallback.accept(reason, 0, 0);
        }
        humanAttention.notifyDesktop(reason);
        long lastAlert = System.currentTimeMillis();
        boolean sawBlock = pageNeedsHuman();
        while (shouldStopCallback == null || !Boolean.TRUE.equals(shouldStopCallback.get())) {
            PlaywrightUtil.sleep(5);
            if (humanAttention.consumeResume()) {
                humanAttention.clear();
                log.info("收到继续指令，恢复筛选");
                return;
            }
            boolean blocked = pageNeedsHuman();
            if (blocked) {
                sawBlock = true;
            }
            if (sawBlock && !blocked) {
                humanAttention.clear();
                log.info("人工处理后验证已消失，继续筛选");
                return;
            }
            if (System.currentTimeMillis() - lastAlert > 60_000) {
                humanAttention.notifyDesktop(reason);
                if (progressCallback != null) {
                    progressCallback.accept(reason, 0, 0);
                }
                lastAlert = System.currentTimeMillis();
            }
        }
        humanAttention.clear();
    }


    private boolean isLoginRequired() {
        try {
            Locator buttonLocator = page.locator(LOGIN_BTNS);
            if (buttonLocator.count() > 0 && buttonLocator.textContent().contains("登录")) {
                return true;
            }
        } catch (Exception e) {
            try {
                page.locator(PAGE_HEADER).waitFor();
                Locator errorLoginLocator = page.locator(ERROR_PAGE_LOGIN);
                if (errorLoginLocator.count() > 0) {
                    errorLoginLocator.click();
                }
                return true;
            } catch (Exception ex) {
                log.info("没有出现403访问异常");
            }
            log.info("cookie有效，已登录...");
            return false;
        }
        return false;
    }

}
