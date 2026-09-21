package com.getjobs.application.controller;

import com.getjobs.worker.manager.PlaywrightManager;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Response;
import com.microsoft.playwright.options.WaitUntilState;
import org.json.JSONArray;
import org.json.JSONObject;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Playwright管理控制器
 * 用于测试和管理Playwright实例
 */
@RestController
@RequestMapping("/api/playwright")
public class PlaywrightController {

    private final PlaywrightManager playwrightManager;

    public PlaywrightController(PlaywrightManager playwrightManager) {
        this.playwrightManager = playwrightManager;
    }

    /**
     * 获取Playwright状态信息
     */
    @GetMapping("/status")
    public ResponseEntity<Map<String, Object>> getStatus() {
        Map<String, Object> status = new HashMap<>();
        status.put("initialized", playwrightManager.isInitialized());
        status.put("cdpPort", playwrightManager.getCdpPort());
        status.put("hasBossPage", playwrightManager.getBossPage() != null);
        // 改用持久化上下文后没有独立的 Browser 对象，context 即代表浏览器本身
        status.put("hasBrowser", playwrightManager.getContext() != null);
        status.put("bossLoggedIn", playwrightManager.isLoggedIn("boss"));

        return ResponseEntity.ok(status);
    }

    /**
     * 指纹自检：确认当前浏览器有没有暴露自动化特征。
     * <p>
     * 期望值：
     * navigator.webdriver = false（真实 Chrome 就是 false，undefined 反而是老式 stealth 脚本的痕迹）；
     * userAgentData 必须存在且 platform/brands 与 UA 自洽；cdc_ 残留为空。
     */
    @GetMapping("/fingerprint")
    public ResponseEntity<Map<String, Object>> fingerprint() {
        try {
            // Playwright 调用必须走专用线程，不能直接在 http-nio 线程上调
            Object raw = playwrightManager.callOnPlaywright(() -> playwrightManager.getBossPage().evaluate("""
                    () => {
                        const uaData = navigator.userAgentData;
                        return {
                            'navigator.webdriver': String(navigator.webdriver),
                            'userAgent': navigator.userAgent,
                            'navigator.platform': navigator.platform,
                            'uaData.platform': uaData ? uaData.platform : '(缺失-异常)',
                            'uaData.brands': uaData && uaData.brands
                                ? uaData.brands.map(b => b.brand + ' ' + b.version).join(', ')
                                : '(缺失-异常)',
                            'cdc_残留': Object.keys(window).filter(k => k.startsWith('cdc_')).join(',') || '(无)',
                            'url': location.href
                        };
                    }"""));
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("fingerprint", raw);
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            Map<String, Object> error = new HashMap<>();
            error.put("success", false);
            error.put("error", e.getMessage());
            return ResponseEntity.internalServerError().body(error);
        }
    }

    /**
     * 诊断：对比"常驻的 bossPage 标签页"和"新开的受控标签页"加载同一地址的表现。
     * <p>
     * 现象是 bossPage 一直转圈加载不完，但在同一个浏览器里手动新开标签页打开同样的地址却正常。
     * 同浏览器同 profile 同指纹，差别只可能在标签页本身，这里把这个变量隔离出来。
     */
    @GetMapping("/diagnose")
    public ResponseEntity<Map<String, Object>> diagnose(
            @RequestParam(defaultValue = "https://www.zhipin.com/web/geek/jobs?query=Java&city=101020100") String url) {
        Map<String, Object> out = new LinkedHashMap<>();
        String probeJs = """
                () => ({
                  readyState: document.readyState,
                  title: document.title,
                  url: location.href,
                  bodyLength: document.body ? document.body.innerHTML.length : 0,
                  jobCards: document.querySelectorAll('li.job-card-box, li.job-card-wrapper').length,
                  listContainers: document.querySelectorAll('ul.rec-job-list, ul.job-list-box, .job-list-box').length,
                  pending: performance.getEntriesByType('resource')
                             .filter(r => r.responseEnd === 0).map(r => r.name).slice(0, 8)
                })""";
        // 刻意不碰常驻的 bossPage：它一旦卡在"永久加载"，evaluate 会无限期阻塞（没有默认超时），
        // 整个诊断请求也会跟着挂死。这里只用全新的受控标签页做对照。
        String[] targets = {"https://www.zhipin.com", url};
        try {
            playwrightManager.callOnPlaywright(() -> {
                for (String target : targets) {
                    Map<String, Object> result = new LinkedHashMap<>();
                    Page probe = null;
                    long start = System.currentTimeMillis();
                    try {
                        probe = playwrightManager.getContext().newPage();
                        probe.setDefaultTimeout(20_000);
                        probe.navigate(target, new Page.NavigateOptions()
                                .setTimeout(20_000)
                                .setWaitUntil(WaitUntilState.DOMCONTENTLOADED));
                        result.put("navigateMs", System.currentTimeMillis() - start);
                        probe.waitForTimeout(5_000);
                        result.put("currentUrl", probe.url());
                        result.put("probe", probe.evaluate(probeJs));
                    } catch (Exception e) {
                        result.put("elapsedMs", System.currentTimeMillis() - start);
                        result.put("error", e.getMessage() == null ? e.toString()
                                : e.getMessage().split("\n")[0]);
                    } finally {
                        if (probe != null) {
                            try {
                                probe.close();
                            } catch (Exception ignored) {
                            }
                        }
                    }
                    out.put(target, result);
                }
                return null;
            });
            out.put("success", true);
        } catch (Exception e) {
            out.put("success", false);
            out.put("error", e.getMessage());
        }
        return ResponseEntity.ok(out);
    }

    /**
     * 实验：桌面列表能不能拿到 HR 活跃、搜索栏有没有活跃度筛。
     * 新开标签，不碰正在用的 bossPage。
     */
    @GetMapping("/probe-active")
    public ResponseEntity<Map<String, Object>> probeActive() {
        String url = "https://www.zhipin.com/web/geek/jobs?city=101210100&jobType=1902"
                + "&experience=108,102&degree=203&query=" + java.net.URLEncoder.encode("AI Agent", java.nio.charset.StandardCharsets.UTF_8);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("url", url);
        try {
            playwrightManager.callOnPlaywright(() -> {
                Page probe = null;
                List<Map<String, Object>> listJobs = new CopyOnWriteArrayList<>();
                try {
                    probe = playwrightManager.getContext().newPage();
                    probe.setDefaultTimeout(25_000);
                    List<Map<String, Object>> apiHits = new CopyOnWriteArrayList<>();
                    probe.onResponse(resp -> {
                        captureJoblist(resp, listJobs);
                        captureZpgeek(resp, apiHits);
                    });
                    probe.navigate(url, new Page.NavigateOptions()
                            .setTimeout(25_000)
                            .setWaitUntil(WaitUntilState.DOMCONTENTLOADED));
                    probe.waitForTimeout(4_000);
                    out.put("listUrl", probe.url());
                    out.put("filters", probe.evaluate("""
                            () => {
                              const roots = [...document.querySelectorAll(
                                '.search-condition, .filter-select-box, .condition-filter, .job-search-wrapper, [class*="filter"]'
                              )].slice(0, 12);
                              return {
                                chipText: roots.map(el => (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 240)),
                                hasActiveWord: document.body.innerText.includes('活跃度')
                                  || document.body.innerText.includes('近3天')
                                  || document.body.innerText.includes('近三天')
                                  || document.body.innerText.includes('只看在线')
                              };
                            }"""));
                    out.put("cards", probe.evaluate("""
                            () => [...document.querySelectorAll('ul.rec-job-list li.job-card-box')].slice(0, 8).map(el => {
                              const a = el.querySelector('a.job-name');
                              const lines = (el.innerText || '').split(/\\n/).map(s => s.trim()).filter(Boolean);
                              const activeNodes = [...el.querySelectorAll(
                                'span.boss-active-time, .boss-online-tag, .boss-online, .active-time, [class*="active"]'
                              )].map(n => ({
                                tag: n.tagName,
                                className: n.className,
                                text: ((n.innerText || n.textContent || '') + '').trim().slice(0, 40)
                              }));
                              return {
                                job: (a && a.innerText || '').trim(),
                                lastLines: lines.slice(-6),
                                activeNodes
                              };
                            })"""));
                    out.put("listJobCount", listJobs.size());
                    if (!listJobs.isEmpty()) {
                        Map<String, Object> sample = listJobs.get(0);
                        out.put("listJobKeys", sample.get("keys"));
                        out.put("listActiveFields", sample.get("active"));
                        out.put("listSamples", listJobs.stream().limit(8).map(m -> m.get("active")).toList());
                    }
                    Map<String, Object> detail = clickFirstDetail(probe);
                    out.put("detail", detail);
                    out.put("zpgeekHits", apiHits.stream().limit(20).toList());
                    out.put("success", true);
                } finally {
                    if (probe != null) {
                        try {
                            probe.close();
                        } catch (Exception ignored) {
                        }
                    }
                }
                return null;
            });
        } catch (Exception e) {
            out.put("success", false);
            out.put("error", e.getMessage());
        }
        return ResponseEntity.ok(out);
    }

    private static void captureJoblist(Response resp, List<Map<String, Object>> sink) {
        try {
            String u = resp.url();
            if (u == null || !u.contains("/wapi/zpgeek/") || !u.contains("joblist")) {
                return;
            }
            String body = resp.text();
            if (body == null || body.isBlank()) {
                return;
            }
            JSONObject root = new JSONObject(body);
            JSONObject zp = root.optJSONObject("zpData");
            JSONArray list = zp != null ? zp.optJSONArray("jobList") : null;
            if (list == null && zp != null) {
                list = zp.optJSONArray("list");
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
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("keys", new ArrayList<>(flattenKeys(job, "")));
                row.put("active", pickActive(job));
                sink.add(row);
            }
        } catch (Throwable ignore) {
        }
    }

    private static Map<String, Object> pickActive(JSONObject job) {
        Map<String, Object> m = new LinkedHashMap<>();
        putIfPresent(m, job, "activeTimeDesc");
        putIfPresent(m, job, "bossOnline");
        putIfPresent(m, job, "activeTime");
        putIfPresent(m, job, "online");
        JSONObject boss = job.optJSONObject("bossInfo");
        if (boss != null) {
            putIfPresent(m, boss, "activeTimeDesc");
            putIfPresent(m, boss, "activeTime");
            m.put("bossInfoKeys", new ArrayList<>(boss.keySet()));
        }
        JSONObject info = job.optJSONObject("jobInfo");
        if (info != null) {
            putIfPresent(m, info, "activeTimeDesc");
        }
        m.put("jobName", job.optString("jobName", ""));
        m.put("brandName", job.optString("brandName", ""));
        return m;
    }

    private static void putIfPresent(Map<String, Object> m, JSONObject o, String key) {
        if (o != null && o.has(key) && !o.isNull(key)) {
            m.put(key, o.opt(key));
        }
    }

    private static Set<String> flattenKeys(JSONObject o, String prefix) {
        Set<String> keys = new LinkedHashSet<>();
        for (String k : o.keySet()) {
            String path = prefix.isEmpty() ? k : prefix + "." + k;
            keys.add(path);
            Object v = o.opt(k);
            if (v instanceof JSONObject child) {
                keys.addAll(flattenKeys(child, path));
            }
        }
        return keys;
    }

    private static void captureZpgeek(Response resp, List<Map<String, Object>> sink) {
        try {
            String u = resp.url();
            if (u == null || !u.contains("/wapi/zpgeek/")) {
                return;
            }
            String body = "";
            try {
                body = resp.text();
            } catch (Throwable ignore) {
            }
            Map<String, Object> hit = new LinkedHashMap<>();
            hit.put("url", u.replaceAll("[?].*", ""));
            hit.put("status", resp.status());
            hit.put("hasActiveTimeDesc", body != null && body.contains("activeTimeDesc"));
            int idx = body == null ? -1 : body.indexOf("activeTimeDesc");
            if (idx >= 0) {
                int end = Math.min(body.length(), idx + 80);
                hit.put("snippet", body.substring(idx, end));
            }
            sink.add(hit);
        } catch (Throwable ignore) {
        }
    }

    private static Map<String, Object> clickFirstDetail(Page probe) {
        Map<String, Object> detail = new LinkedHashMap<>();
        try {
            var name = probe.locator("ul.rec-job-list li.job-card-box a.job-name").first();
            if (name.count() == 0) {
                detail.put("error", "no cards");
                return detail;
            }
            try {
                Response resp = probe.waitForResponse(
                        r -> {
                            String u = r.url();
                            return u != null && u.contains("/wapi/zpgeek/") && u.contains("detail");
                        },
                        new Page.WaitForResponseOptions().setTimeout(12_000),
                        name::click);
                JSONObject root = new JSONObject(resp.text());
                JSONObject zp = root.optJSONObject("zpData");
                JSONObject boss = zp != null ? zp.optJSONObject("bossInfo") : null;
                detail.put("detailUrl", resp.url().replaceAll("[?].*", ""));
                if (boss != null) {
                    detail.put("activeTimeDesc", boss.opt("activeTimeDesc"));
                    detail.put("bossKeys", new ArrayList<>(boss.keySet()));
                }
            } catch (Exception e) {
                name.click();
                detail.put("waitError", e.getMessage() == null ? e.toString() : e.getMessage().split("\n")[0]);
            }
            probe.waitForTimeout(2_500);
            Object dom = probe.evaluate("""
                    () => {
                      const n = document.querySelector('span.boss-active-time, .boss-active-time, .boss-online-tag');
                      const panel = document.querySelector('.job-detail-box, .job-detail, [class*="job-detail"]');
                      const text = (document.body && document.body.innerText) || '';
                      const hit = text.match(/(.{0,12}(在线|刚刚活跃|今日活跃|今天活跃|[0-9]日内活跃|[0-9]天内活跃|本周活跃|[0-9]周内活跃|本月活跃).{0,12})/);
                      return {
                        node: n ? (n.innerText || '').trim() : '',
                        panelTail: panel ? (panel.innerText || '').trim().slice(-500) : '',
                        bodyHit: hit ? hit[0] : ''
                      };
                    }""");
            detail.put("dom", dom);
        } catch (Exception e) {
            detail.put("error", e.getMessage() == null ? e.toString() : e.getMessage().split("\n")[0]);
        }
        return detail;
    }

    /**
     * 测试Boss导航功能
     */
    @GetMapping("/test-navigate")
    public ResponseEntity<Map<String, String>> testNavigate() {
        try {
            playwrightManager.getBossPage().navigate("https://www.zhipin.com");
            String title = playwrightManager.getBossPage().title();

            Map<String, String> result = new HashMap<>();
            result.put("success", "true");
            result.put("title", title);
            result.put("url", playwrightManager.getBossPage().url());

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("success", "false");
            error.put("error", e.getMessage());
            return ResponseEntity.internalServerError().body(error);
        }
    }
}
