package com.getjobs.worker.manager;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.getjobs.application.service.CookieService;
import com.microsoft.playwright.*;
import com.microsoft.playwright.options.Cookie;
import com.microsoft.playwright.options.LoadState;
import com.microsoft.playwright.options.WaitUntilState;
import jakarta.annotation.PreDestroy;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/**
 * Playwright 管理器：只开 Boss 一个站。
 */
@Slf4j
@Getter
@Component
@Lazy
public class PlaywrightManager {

    private Playwright playwright;
    private volatile boolean browserClosed = false;
    private BrowserContext context;
    private Page bossPage;

    private final Map<String, Boolean> loginStatus = new ConcurrentHashMap<>();
    private final List<Consumer<LoginStatusChange>> loginStatusListeners = new CopyOnWriteArrayList<>();
    private volatile boolean bossMonitoringPaused = false;

    private static final int DEFAULT_TIMEOUT = 30000;
    private static final int CDP_PORT = 7866;
    private static final double LOCATOR_PROBE_TIMEOUT = 5000;
    private static final double LOAD_STATE_TIMEOUT = 10_000;
    private static final Set<String> BOSS_LOGIN_COOKIES = Set.of("bst", "wt2", "zp_at", "geek_zp_token");
    private static final Path USER_DATA_DIR = Paths.get(System.getProperty("user.dir"), "browser-data");
    private static final String BOSS_URL = "https://www.zhipin.com";
    private static final String BOSS_ENTRY_URL = "https://www.zhipin.com/web/geek/jobs";
    private static final String BOSS_DOMAIN = "zhipin.com";

    @Autowired
    private CookieService cookieService;

    private static final String PW_THREAD_NAME = "playwright-thread";

    private final ExecutorService playwrightExecutor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, PW_THREAD_NAME);
        thread.setDaemon(true);
        return thread;
    });

    private final AtomicInteger playwrightQueueDepth = new AtomicInteger();

    private boolean onPlaywrightThread() {
        return PW_THREAD_NAME.equals(Thread.currentThread().getName());
    }

    public <T> T callOnPlaywright(Callable<T> task) {
        if (onPlaywrightThread()) {
            try {
                return task.call();
            } catch (Exception e) {
                throw toRuntime(e);
            }
        }
        playwrightQueueDepth.incrementAndGet();
        try {
            return playwrightExecutor.submit(() -> {
                try {
                    return task.call();
                } finally {
                    playwrightQueueDepth.decrementAndGet();
                }
            }).get();
        } catch (ExecutionException e) {
            throw toRuntime(e.getCause());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("等待Playwright任务被中断", e);
        }
    }

    public void runOnPlaywright(Runnable task) {
        callOnPlaywright(() -> {
            task.run();
            return null;
        });
    }

    public boolean tryRunOnPlaywright(Runnable task) {
        if (playwrightQueueDepth.get() > 0) {
            return false;
        }
        playwrightQueueDepth.incrementAndGet();
        playwrightExecutor.execute(() -> {
            try {
                task.run();
            } catch (Exception e) {
                log.debug("Playwright后台任务异常: {}", e.getMessage());
            } finally {
                playwrightQueueDepth.decrementAndGet();
            }
        });
        return true;
    }

    private void sanitizeProfileExitState() {
        Path preferences = USER_DATA_DIR.resolve("Default").resolve("Preferences");
        if (!Files.isRegularFile(preferences)) {
            return;
        }
        try {
            ObjectMapper mapper = new ObjectMapper();
            JsonNode root = mapper.readTree(preferences.toFile());
            if (!(root instanceof ObjectNode rootNode)) {
                return;
            }
            JsonNode profile = rootNode.get("profile");
            if (!(profile instanceof ObjectNode profileNode)) {
                return;
            }
            String exitType = profileNode.path("exit_type").asText("");
            boolean exitedCleanly = profileNode.path("exited_cleanly").asBoolean(true);
            if ("Normal".equals(exitType) && exitedCleanly) {
                return;
            }
            profileNode.put("exit_type", "Normal");
            profileNode.put("exited_cleanly", true);
            mapper.writeValue(preferences.toFile(), rootNode);
            log.info("已清除浏览器 profile 的崩溃退出标记（原 exit_type={}），避免弹出\"要恢复页面吗？\"", exitType);
        } catch (Exception e) {
            log.warn("清理 profile 退出状态失败（不影响启动）: {}", e.getMessage());
        }
    }

    public boolean isPlaywrightBusy() {
        return playwrightQueueDepth.get() > 0;
    }

    private static RuntimeException toRuntime(Throwable throwable) {
        if (throwable instanceof RuntimeException runtimeException) {
            return runtimeException;
        }
        return new RuntimeException(throwable);
    }

    public void init() {
        if (isInitialized()) {
            return;
        }
        runOnPlaywright(this::initInternal);
    }

    private void initInternal() {
        if (isInitialized()) {
            return;
        }
        log.info("初始化 Boss 浏览器");

        try {
            playwright = createPlaywright();
            log.info("Playwright 已启动 ({})", describeDriver());
            sanitizeProfileExitState();

            context = playwright.chromium().launchPersistentContext(USER_DATA_DIR,
                    new BrowserType.LaunchPersistentContextOptions()
                            .setChannel("chrome")
                            .setHeadless(false)
                            .setSlowMo(50)
                            .setViewportSize(null)
                            .setChromiumSandbox(true)
                            .setArgs(List.of(
                                    "--start-maximized",
                                    "--test-type",
                                    "--disable-session-crashed-bubble",
                                    "--hide-crash-restore-bubble",
                                    "--no-first-run",
                                    "--no-default-browser-check",
                                    "--no-proxy-server",
                                    "--proxy-bypass-list=*",
                                    "--disable-blink-features=AutomationControlled"
                            )));
            browserClosed = false;
            context.onClose(closed -> {
                browserClosed = true;
                log.warn("检测到浏览器已关闭，下次操作会自动重新初始化");
            });
            log.info("Chrome 已启动（持久化上下文: {}）", USER_DATA_DIR);

            List<Page> startupPages = new ArrayList<>(context.pages());
            bossPage = context.newPage();
            bossPage.setDefaultTimeout(DEFAULT_TIMEOUT);
            for (Page startup : startupPages) {
                try {
                    startup.close();
                } catch (Exception e) {
                    log.debug("关闭启动空白页失败（忽略）: {}", e.getMessage());
                }
            }

            setupBossPlatform();
            log.info("Boss 浏览器初始化完成");
        } catch (Exception e) {
            log.error("浏览器初始化失败", e);
            throw new RuntimeException("Playwright初始化失败", e);
        }
    }

    private Playwright createPlaywright() {
        if (System.getProperty("playwright.cli.dir") == null) {
            Path driverDir = locatePatchrightDriver();
            if (driverDir != null) {
                System.setProperty("playwright.cli.dir", driverDir.toString());
            } else {
                log.warn("未找到 patchright driver，将退回官方 driver-bundle。请先执行: gradlew installPatchrightDriver");
            }
        }

        Map<String, String> env = new HashMap<>();
        if (System.getProperty("playwright.cli.dir") != null && System.getenv("PLAYWRIGHT_NODEJS_PATH") == null) {
            String nodePath = locateNodeExecutable();
            if (nodePath != null) {
                env.put("PLAYWRIGHT_NODEJS_PATH", nodePath);
                log.info("使用本机 node: {}", nodePath);
            } else {
                log.warn("PATH 里没找到 node，patchright driver 可能起不来");
            }
        }

        return env.isEmpty()
                ? Playwright.create()
                : Playwright.create(new Playwright.CreateOptions().setEnv(env));
    }

    private Path locatePatchrightDriver() {
        Path projectDir = Paths.get(System.getProperty("user.dir"));
        List<Path> candidates = List.of(
                projectDir.resolve("build").resolve("patchright-driver"),
                projectDir.resolve("patchright-driver"),
                projectDir.getParent() == null ? projectDir
                        : projectDir.getParent().resolve("build").resolve("patchright-driver"));
        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate.resolve("package").resolve("cli.js"))) {
                return candidate.toAbsolutePath();
            }
        }
        return null;
    }

    private String locateNodeExecutable() {
        boolean windows = System.getProperty("os.name").toLowerCase(Locale.ROOT).contains("windows");
        String exe = windows ? "node.exe" : "node";
        String path = System.getenv("PATH");
        if (path == null) {
            return null;
        }
        for (String entry : path.split(java.io.File.pathSeparator)) {
            if (entry == null || entry.isBlank()) {
                continue;
            }
            try {
                Path candidate = Paths.get(entry.trim()).resolve(exe);
                if (Files.isRegularFile(candidate)) {
                    return candidate.toAbsolutePath().toString();
                }
            } catch (Exception ignore) {
            }
        }
        return null;
    }

    private String describeDriver() {
        String cliDir = System.getProperty("playwright.cli.dir");
        if (cliDir == null || cliDir.isBlank()) {
            return "官方 driver-bundle";
        }
        return "patchright @ " + cliDir;
    }

    private void setupBossPlatform() {
        log.info("开始初始化 Boss...");
        try {
            if (hasBossLoginCookies()) {
                log.info("持久化画像已有 Boss 登录 Cookie");
            } else {
                log.info("画像无 Boss 登录 Cookie，等你在 Chrome 里登录");
            }
        } catch (Exception e) {
            log.warn("从数据库加载 Boss Cookie 失败: {}", e.getMessage());
        }

        int maxRetries = 3;
        boolean navigateSuccess = false;
        for (int attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                bossPage.navigate(BOSS_ENTRY_URL, new Page.NavigateOptions()
                        .setTimeout(60000)
                        .setWaitUntil(WaitUntilState.DOMCONTENTLOADED));
                navigateSuccess = true;
                break;
            } catch (Exception e) {
                boolean pageAccessible = false;
                try {
                    String url = bossPage.url();
                    pageAccessible = url != null && url.contains("zhipin.com");
                } catch (Exception ignored) {
                }
                if (pageAccessible) {
                    navigateSuccess = true;
                    break;
                }
                if (attempt < maxRetries) {
                    try {
                        Thread.sleep(2000);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    }
                }
            }
        }

        if (!navigateSuccess) {
            log.warn("Boss 页面导航失败");
        }

        try {
            bossPage.waitForLoadState(LoadState.NETWORKIDLE,
                    new Page.WaitForLoadStateOptions().setTimeout(LOAD_STATE_TIMEOUT));
        } catch (Exception e) {
            log.debug("等待 Boss 页面网络空闲失败: {}", e.getMessage());
        }

        setLoginStatus("boss", checkIfLoggedIn());
        setupLoginMonitoring(bossPage);
    }

    private boolean hasBossLoginCookies() {
        try {
            for (Cookie cookie : context.cookies(BOSS_URL)) {
                if (BOSS_LOGIN_COOKIES.contains(cookie.name)
                        && cookie.value != null && !cookie.value.isBlank()) {
                    return true;
                }
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    private boolean checkIfLoggedIn() {
        if (hasBossLoginCookies()) {
            return true;
        }
        try {
            Locator userLabel = bossPage.locator("li.nav-figure span.label-text").first();
            if (isVisibleQuick(userLabel)) {
                return true;
            }
        } catch (Exception ignored) {
        }
        try {
            Locator navFigure = bossPage.locator("li.nav-figure").first();
            if (isVisibleQuick(navFigure)) {
                return true;
            }
        } catch (Exception ignored) {
        }
        try {
            Locator loginAnchor = bossPage.locator("li.nav-sign a, .btns").first();
            if (isVisibleQuick(loginAnchor)) {
                String text = loginAnchor.textContent(new Locator.TextContentOptions().setTimeout(LOCATOR_PROBE_TIMEOUT));
                if (text != null && text.contains("登录")) {
                    return false;
                }
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    private boolean isVisibleQuick(Locator locator) {
        try {
            return locator.isVisible(new Locator.IsVisibleOptions().setTimeout(LOCATOR_PROBE_TIMEOUT));
        } catch (Exception e) {
            return false;
        }
    }

    private void setupLoginMonitoring(Page page) {
        page.onFrameNavigated(frame -> {
            if (frame == page.mainFrame()) {
                if (!bossMonitoringPaused && !isPlaywrightBusy()) {
                    checkLoginStatus();
                }
            }
        });
        log.info("Boss 登录状态监控已启用");
    }

    private void checkLoginStatus() {
        try {
            boolean isLoggedIn = checkIfLoggedIn();
            Boolean previousStatus = loginStatus.get("boss");
            if (isLoggedIn && (previousStatus == null || !previousStatus)) {
                onLoginSuccess();
            }
        } catch (Exception e) {
            log.debug("检查 Boss 登录状态时发生异常: {}", e.getMessage());
        }
    }

    private void onLoginSuccess() {
        log.info("Boss 登录成功");
        setLoginStatus("boss", true);
        saveBossCookiesToDatabase("login success");
    }

    private volatile int lastBossCookieCount = -1;

    private void saveBossCookiesToDatabase(String remark) {
        try {
            List<Cookie> cookies = filterCookiesByDomain(context.cookies(), BOSS_DOMAIN);
            String cookieJson = new ObjectMapper().writeValueAsString(cookies);
            boolean result = cookieService.saveOrUpdateCookie("boss", cookieJson, remark);
            if (result && (cookies.size() != lastBossCookieCount || !"periodic".equals(remark))) {
                log.info("保存 Boss Cookie 成功，共 {} 条，remark={}", cookies.size(), remark);
                lastBossCookieCount = cookies.size();
            }
        } catch (Exception e) {
            log.warn("保存 Boss Cookie 失败: {}", e.getMessage());
        }
    }

    @Scheduled(fixedDelay = 20000)
    public void persistBossCookiesWhileAlive() {
        if (playwright == null || context == null || browserClosed) {
            return;
        }
        tryRunOnPlaywright(() -> {
            try {
                if (hasBossLoginCookies()) {
                    saveBossCookiesToDatabase("periodic");
                }
            } catch (Exception e) {
                log.debug("定期保存 Boss Cookie 失败: {}", e.getMessage());
            }
        });
    }

    public void saveBossCookiesToDb(String remark) {
        saveBossCookiesToDatabase(remark);
    }

    public void saveCookiesToDb(String platform, String remark) {
        if (!"boss".equals(platform)) {
            throw new IllegalArgumentException("只支持 boss: " + platform);
        }
        saveBossCookiesToDatabase(remark);
    }

    public void clearBossCookies() {
        try {
            if (context != null) {
                context.clearCookies();
                log.info("已清理上下文 Cookie");
            }
        } catch (Exception e) {
            log.error("清理 Cookie 失败: {}", e.getMessage(), e);
            throw new RuntimeException("清理 Cookie 失败", e);
        }
    }

    @Scheduled(fixedDelay = 3000)
    public void scheduledLoginCheck() {
        if (playwright == null || context == null) {
            return;
        }
        tryRunOnPlaywright(() -> {
            try {
                if (bossPage != null && !bossMonitoringPaused) {
                    checkLoginStatus();
                }
            } catch (Exception e) {
                log.debug("定时登录检测异常: {}", e.getMessage());
            }
        });
    }

    public void pauseBossMonitoring() {
        bossMonitoringPaused = true;
    }

    public void resumeBossMonitoring() {
        bossMonitoringPaused = false;
    }

    @PreDestroy
    public void destroy() {
        log.info("关闭 Playwright...");
        try {
            if (context != null && !browserClosed) {
                saveBossCookiesToDatabase("shutdown");
            }
            if (bossPage != null) {
                bossPage.close();
            }
            if (context != null) {
                context.close();
            }
            if (playwright != null) {
                playwright.close();
            }
        } catch (Exception e) {
            log.error("关闭 Playwright 时发生错误", e);
        }
    }

    public boolean isInitialized() {
        return playwright != null && context != null && bossPage != null && !browserClosed;
    }

    public synchronized void ensureReady() {
        if (isInitialized()) {
            return;
        }
        log.warn("浏览器不可用，正在重新初始化...");
        try {
            if (playwright != null) {
                playwright.close();
            }
        } catch (Exception ignored) {
        }
        playwright = null;
        context = null;
        bossPage = null;
        browserClosed = false;
        loginStatus.clear();
        init();
    }

    public int getCdpPort() {
        return CDP_PORT;
    }

    public void addLoginStatusListener(Consumer<LoginStatusChange> listener) {
        loginStatusListeners.add(listener);
    }

    public void removeLoginStatusListener(Consumer<LoginStatusChange> listener) {
        loginStatusListeners.remove(listener);
    }

    public boolean isLoggedIn(String platform) {
        return loginStatus.getOrDefault(platform, false);
    }

    public void setLoginStatus(String platform, boolean isLoggedIn) {
        Boolean previousStatus = loginStatus.get(platform);
        if (previousStatus != null && previousStatus == isLoggedIn) {
            return;
        }
        loginStatus.put(platform, isLoggedIn);

        if ("boss".equals(platform) && !isLoggedIn) {
            try {
                if (bossPage != null) {
                    String currentUrl = null;
                    try {
                        currentUrl = bossPage.url();
                    } catch (Exception ignored) {
                    }
                    if (currentUrl == null || !currentUrl.contains("/web/user/")) {
                        bossPage.navigate(BOSS_URL + "/web/user/?ka=header-login");
                        try {
                            Thread.sleep(800);
                        } catch (InterruptedException ie) {
                            Thread.currentThread().interrupt();
                        }
                    }
                    try {
                        Locator qrSwitch = bossPage.locator(".btn-sign-switch.ewm-switch").first();
                        if (isVisibleQuick(qrSwitch)) {
                            qrSwitch.click();
                        } else {
                            Locator tip = bossPage.getByText("APP扫码登录").first();
                            if (isVisibleQuick(tip)) {
                                tip.click();
                            } else {
                                Locator legacy = bossPage.locator("li.sign-switch-tip").first();
                                if (isVisibleQuick(legacy)) {
                                    legacy.click();
                                }
                            }
                        }
                    } catch (Exception e) {
                        log.debug("切换二维码登录失败: {}", e.getMessage());
                    }
                }
            } catch (Exception e) {
                log.debug("Boss 未登录引导失败: {}", e.getMessage());
            }
        }

        LoginStatusChange change = new LoginStatusChange(platform, isLoggedIn, System.currentTimeMillis());
        loginStatusListeners.forEach(listener -> {
            try {
                listener.accept(change);
            } catch (Exception e) {
                log.error("通知登录状态监听器失败: platform={}, isLoggedIn={}", platform, isLoggedIn, e);
            }
        });
    }

    private List<Cookie> parseCookiesFromString(String cookieJson) {
        List<Cookie> cookies = new ArrayList<>();
        try {
            ObjectMapper objectMapper = new ObjectMapper();
            JsonNode jsonArray = objectMapper.readTree(cookieJson);
            for (JsonNode node : jsonArray) {
                Cookie cookie = new Cookie(node.get("name").asText(), node.get("value").asText());
                if (node.has("domain") && !node.get("domain").isNull()) {
                    cookie.domain = node.get("domain").asText();
                }
                if (node.has("path") && !node.get("path").isNull()) {
                    cookie.path = node.get("path").asText();
                }
                if (node.has("expires") && !node.get("expires").isNull()) {
                    cookie.expires = node.get("expires").asDouble();
                }
                if (node.has("httpOnly") && !node.get("httpOnly").isNull()) {
                    cookie.httpOnly = node.get("httpOnly").asBoolean();
                }
                if (node.has("secure") && !node.get("secure").isNull()) {
                    cookie.secure = node.get("secure").asBoolean();
                }
                if (node.has("sameSite") && !node.get("sameSite").isNull()) {
                    String sameSite = node.get("sameSite").asText();
                    if (sameSite != null && !sameSite.isEmpty()) {
                        cookie.sameSite = com.microsoft.playwright.options.SameSiteAttribute.valueOf(
                                sameSite.toUpperCase());
                    }
                }
                cookies.add(cookie);
            }
        } catch (Exception e) {
            log.error("解析 Cookie JSON 失败: {}", e.getMessage(), e);
        }
        return cookies;
    }

    private List<Cookie> filterCookiesByDomain(List<Cookie> cookies, String domainSuffix) {
        if (cookies == null || cookies.isEmpty()) {
            return new ArrayList<>();
        }
        String suffix = domainSuffix == null ? "" : domainSuffix.toLowerCase(Locale.ROOT);
        List<Cookie> filtered = new ArrayList<>();
        for (Cookie cookie : cookies) {
            if (cookie == null || cookie.domain == null || cookie.domain.isBlank()) {
                continue;
            }
            String domain = cookie.domain.toLowerCase(Locale.ROOT);
            if (domain.equals(suffix) || domain.endsWith("." + suffix)) {
                filtered.add(cookie);
            }
        }
        return filtered;
    }

    public record LoginStatusChange(String platform, boolean isLoggedIn, long timestamp) {
    }
}
