package com.getjobs.application.service;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.dataformat.yaml.YAMLGenerator;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 本机运行配置：只读 boss.yaml。已开聊记录仍是 opened-chats.jsonl。
 */
@Slf4j
@Service
public class LocalBossSettings {

    private static final Path SEARCH = Path.of("boss.yaml");
    private static final Path OPENED = Path.of("opened-chats.jsonl");
    private static final Pattern SCREEN_FILE =
            Pattern.compile("^(\\d{8}-\\d{6})_([^_]+)_(.+)\\.jsonl$");
    private static final DateTimeFormatter SCREEN_STAMP =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneId.systemDefault());

    private volatile Path currentScreenFile;
    private volatile String screenRunStamp;

    private final ObjectMapper yaml = new ObjectMapper(
            new YAMLFactory().disable(YAMLGenerator.Feature.WRITE_DOC_START_MARKER));
    private final ObjectMapper json = new ObjectMapper();

    public SearchFile loadSearch() {
        if (!Files.isRegularFile(SEARCH)) {
            throw new IllegalStateException("缺少 " + SEARCH.toAbsolutePath());
        }
        try {
            SearchFile file = yaml.readValue(SEARCH.toFile(), SearchFile.class);
            if (file == null) {
                throw new IllegalStateException(SEARCH + " 是空的");
            }
            return file;
        } catch (IOException e) {
            throw new IllegalStateException("读取 " + SEARCH + " 失败: " + e.getMessage(), e);
        }
    }

    public synchronized void saveSearch(SearchFile file) {
        try {
            yaml.writeValue(SEARCH.toFile(), file);
        } catch (IOException e) {
            throw new IllegalStateException("写入 " + SEARCH + " 失败: " + e.getMessage(), e);
        }
    }

    public String loadGreeting() {
        String text = loadSearch().getGreeting();
        if (text == null || text.isBlank()) {
            throw new IllegalStateException("boss.yaml 的 greeting 不能为空");
        }
        return text.trim();
    }

    public BlacklistFile loadBlacklist() {
        BlacklistFile file = loadSearch().getBlacklist();
        return file != null ? file : new BlacklistFile();
    }

    public Path screenResultsDir() {
        SearchFile file = loadSearch();
        String dirRaw = file.getScreenResultsDir();
        if (dirRaw != null && !dirRaw.isBlank()) {
            return resolvePath(dirRaw.trim());
        }
        String legacy = file.getScreenResults();
        if (legacy != null && !legacy.isBlank()) {
            Path p = resolvePath(legacy.trim());
            Path parent = p.getParent();
            return parent != null ? parent : Path.of(System.getProperty("user.dir", "."));
        }
        return resolvePath("screen-results");
    }

    public Path screenResultsPath() {
        Path cur = currentScreenFile;
        if (cur != null) {
            return cur;
        }
        List<Map<String, Object>> files = listScreenFiles();
        if (!files.isEmpty()) {
            return resolveListedFile(String.valueOf(files.get(0).get("name")));
        }
        throw new IllegalStateException("还没有筛选结果 jsonl");
    }

    public Path currentScreenFile() {
        return currentScreenFile;
    }

    public void setCurrentScreenFile(Path path) {
        currentScreenFile = path;
    }

    /** 一次筛选共用一枚时间戳；每个搜词一份 jsonl，前缀相同。 */
    public synchronized void beginScreenRun() {
        screenRunStamp = SCREEN_STAMP.format(Instant.now());
        currentScreenFile = null;
    }

    public synchronized Path createKeywordScreenFile(String jobType, String keyword) {
        Path dir = screenResultsDir();
        try {
            Files.createDirectories(dir);
            String stamp = screenRunStamp;
            if (stamp == null || stamp.isBlank()) {
                stamp = SCREEN_STAMP.format(Instant.now());
                screenRunStamp = stamp;
            }
            String name = stamp + "_" + slug(jobType) + "_" + slug(keyword) + ".jsonl";
            Path file = dir.resolve(name);
            Files.writeString(file, "", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            currentScreenFile = file;
            return file;
        } catch (IOException e) {
            throw new IllegalStateException("无法创建筛选结果: " + e.getMessage(), e);
        }
    }

    public List<Map<String, Object>> listScreenFiles() {
        Map<String, Path> found = new LinkedHashMap<>();
        addJsonl(found, screenResultsDir());
        addJsonl(found, Path.of(System.getProperty("user.dir", ".")));
        List<Map<String, Object>> out = new ArrayList<>();
        for (Path path : found.values()) {
            out.add(describeScreenFile(path));
        }
        out.sort(Comparator.<Map<String, Object>>comparingLong(
                m -> ((Number) m.getOrDefault("mtime", 0L)).longValue()).reversed());
        return out;
    }

    public Path resolveListedFile(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("缺少筛选结果文件名");
        }
        String base = Path.of(name.trim()).getFileName().toString();
        if (!base.equals(name.trim()) || !base.endsWith(".jsonl") || base.contains("..")) {
            throw new IllegalArgumentException("非法筛选结果文件名");
        }
        Path inDir = screenResultsDir().resolve(base).normalize();
        Path dir = screenResultsDir().toAbsolutePath().normalize();
        if (inDir.toAbsolutePath().normalize().startsWith(dir) && Files.isRegularFile(inDir)) {
            return inDir;
        }
        Path cwd = Path.of(System.getProperty("user.dir", ".")).resolve(base).normalize();
        if (cwd.getFileName().toString().equals(base) && Files.isRegularFile(cwd)) {
            return cwd;
        }
        throw new IllegalArgumentException("找不到筛选结果: " + base);
    }

    private static Path resolvePath(String raw) {
        Path path = Path.of(raw);
        if (!path.isAbsolute()) {
            path = Path.of(System.getProperty("user.dir", ".")).resolve(path).normalize();
        }
        return path;
    }

    private static void addJsonl(Map<String, Path> found, Path dir) {
        if (!Files.isDirectory(dir)) {
            return;
        }
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir, "*.jsonl")) {
            for (Path p : ds) {
                String name = p.getFileName().toString();
                if ("opened-chats.jsonl".equals(name)) {
                    continue;
                }
                found.putIfAbsent(name, p);
            }
        } catch (IOException ignore) {
        }
    }

    private Map<String, Object> describeScreenFile(Path path) {
        Map<String, Object> m = new LinkedHashMap<>();
        String name = path.getFileName().toString();
        m.put("name", name);
        Matcher g = SCREEN_FILE.matcher(name);
        if (g.matches()) {
            m.put("startedAt", g.group(1));
            m.put("jobType", g.group(2));
            m.put("keyword", g.group(3).replace('-', ' '));
        }
        try {
            m.put("mtime", Files.getLastModifiedTime(path).toMillis());
            int rows = 0;
            for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
                if (line != null && !line.isBlank()) {
                    rows++;
                }
            }
            m.put("rows", rows);
        } catch (IOException e) {
            m.put("mtime", 0L);
            m.put("rows", 0);
        }
        return m;
    }

    static String slug(String raw) {
        if (raw == null || raw.isBlank()) {
            return "na";
        }
        String s = raw.trim().replaceAll("[\\\\/:*?\"<>|\\s]+", "-");
        s = s.replaceAll("-+", "-");
        s = s.replaceAll("^-|-$", "");
        if (s.length() > 80) {
            s = s.substring(0, 80);
        }
        return s.isEmpty() ? "na" : s;
    }

    /**
     * 0 不点详情；负数不设上限；正数是本轮最多点几次。缺省按 0。
     */
    public int detailLimit() {
        Integer n = loadSearch().getDetailLimit();
        return n == null ? 0 : n;
    }

    /**
     * yaml {@code onRisk}：{@code stop} 遇风控结束本轮，{@code wait} 暂停等人。
     */
    public boolean stopOnRisk() {
        return "stop".equals(normalizedOnRisk());
    }

    public String normalizedOnRisk() {
        String v = loadSearch().getOnRisk();
        if (v == null || v.isBlank()) {
            throw new IllegalStateException("boss.yaml 的 onRisk 不能为空，填 stop 或 wait");
        }
        String t = v.trim().toLowerCase(java.util.Locale.ROOT);
        if (!"stop".equals(t) && !"wait".equals(t)) {
            throw new IllegalStateException("boss.yaml 的 onRisk 只能是 stop 或 wait，现在是: " + v);
        }
        return t;
    }

    public int keywordGapSeconds() {
        Integer n = loadSearch().getKeywordGapSeconds();
        if (n == null || n < 0) {
            return 300;
        }
        return n;
    }

    public List<String> companyTokens() {
        RulesFile rules = loadSearch().getRules();
        if (rules == null || rules.getCompanyTokens() == null) {
            return List.of();
        }
        return rules.getCompanyTokens();
    }

    public List<String> jobTitleTokens() {
        RulesFile rules = loadSearch().getRules();
        if (rules == null || rules.getJobTitleTokens() == null) {
            return List.of();
        }
        return rules.getJobTitleTokens();
    }

    public String candidateProfile() {
        String text = loadSearch().getCandidateProfile();
        return text == null ? "" : text;
    }

    public String titlePrompt() {
        PromptsFile prompts = loadSearch().getPrompts();
        if (prompts == null || prompts.getTitle() == null || prompts.getTitle().isBlank()) {
            throw new IllegalStateException("boss.yaml 的 prompts.title 不能为空");
        }
        return prompts.getTitle();
    }

    public String jdPrompt() {
        PromptsFile prompts = loadSearch().getPrompts();
        if (prompts == null || prompts.getJd() == null || prompts.getJd().isBlank()) {
            throw new IllegalStateException("boss.yaml 的 prompts.jd 不能为空");
        }
        return prompts.getJd();
    }

    public String fill(String template, Map<String, String> vars) {
        String out = template == null ? "" : template;
        if (vars == null) {
            return out;
        }
        for (Map.Entry<String, String> e : vars.entrySet()) {
            out = out.replace("{" + e.getKey() + "}", e.getValue() == null ? "" : e.getValue());
        }
        return out;
    }

    public String codeOf(String type, String name) {
        if (name == null || name.isBlank()) {
            return null;
        }
        String key = name.trim();
        Map<String, Map<String, String>> codes = loadSearch().getCodes();
        if (codes == null) {
            throw new IllegalStateException("boss.yaml 的 codes 不能为空");
        }
        Map<String, String> table = codes.get(type);
        if (table == null || table.isEmpty()) {
            throw new IllegalArgumentException("boss.yaml 的 codes." + type + " 没有表");
        }
        String code = table.get(key);
        if (code != null && !code.isBlank()) {
            return code;
        }
        for (String existing : table.values()) {
            if (key.equals(existing)) {
                return key;
            }
        }
        throw new IllegalArgumentException("boss.yaml 的 " + type + " 无法对应 Boss 选项: " + key);
    }

    public Map<String, String> aiConfigs() {
        AiFile ai = loadSearch().getAi();
        if (ai == null) {
            throw new IllegalStateException("boss.yaml 的 ai 不能为空");
        }
        if (ai.getBaseUrl() == null || ai.getBaseUrl().isBlank()
                || ai.getApiKey() == null || ai.getApiKey().isBlank()
                || ai.getModel() == null || ai.getModel().isBlank()) {
            throw new IllegalStateException("boss.yaml 的 ai.baseUrl / ai.apiKey / ai.model 不能为空");
        }
        Map<String, String> map = new LinkedHashMap<>();
        map.put("BASE_URL", ai.getBaseUrl().trim());
        map.put("API_KEY", ai.getApiKey().trim());
        map.put("MODEL", ai.getModel().trim());
        return map;
    }

    public Set<String> openedEncryptIds() {
        LinkedHashSet<String> ids = new LinkedHashSet<>();
        if (!Files.isRegularFile(OPENED)) {
            return ids;
        }
        try {
            for (String line : Files.readAllLines(OPENED, StandardCharsets.UTF_8)) {
                if (line == null || line.isBlank()) {
                    continue;
                }
                String trimmed = line.trim();
                if (trimmed.startsWith("{")) {
                    String id = json.readTree(trimmed).path("encryptId").asText("");
                    if (!id.isBlank()) {
                        ids.add(id);
                    }
                } else {
                    ids.add(trimmed);
                }
            }
        } catch (IOException e) {
            log.warn("读取已开聊失败: {}", e.getMessage());
        }
        return ids;
    }

    public synchronized void recordOpened(String encryptId, String company, String jobName) {
        if (encryptId == null || encryptId.isBlank()) {
            return;
        }
        try {
            String row = String.format(
                    "{\"encryptId\":%s,\"company\":%s,\"job\":%s,\"at\":%s}%n",
                    jsonStr(encryptId), jsonStr(company), jsonStr(jobName), jsonStr(Instant.now().toString()));
            Files.writeString(OPENED, row, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            log.warn("写入已开聊失败: {}", e.getMessage());
        }
    }

    public synchronized void addToBlacklist(String type, String value) {
        if (value == null || value.isBlank()) {
            return;
        }
        SearchFile search = loadSearch();
        if (search.getBlacklist() == null) {
            search.setBlacklist(new BlacklistFile());
        }
        BlacklistFile file = search.getBlacklist();
        List<String> target;
        if ("job".equals(type)) {
            if (file.jobs == null) {
                file.jobs = new ArrayList<>();
            }
            target = file.jobs;
        } else if ("recruiter".equals(type)) {
            if (file.recruiters == null) {
                file.recruiters = new ArrayList<>();
            }
            target = file.recruiters;
        } else {
            if (file.companies == null) {
                file.companies = new ArrayList<>();
            }
            target = file.companies;
        }
        if (target.stream().anyMatch(value::equals)) {
            return;
        }
        target.add(value);
        saveSearch(search);
    }

    private static String jsonStr(String raw) {
        if (raw == null) {
            return "null";
        }
        return "\"" + raw.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class SearchFile {
        private List<String> keywords = new ArrayList<>();
        private List<String> cities = new ArrayList<>();
        private String jobType = "";
        private List<String> experience = new ArrayList<>();
        private List<String> degree = new ArrayList<>();
        private List<String> industry = new ArrayList<>();
        private List<String> salary = new ArrayList<>();
        private List<String> scale = new ArrayList<>();
        private List<String> stage = new ArrayList<>();
        private Integer waitTime = 18;
        private Integer keywordGapSeconds = 300;
        private Boolean sendImgResume = false;
        private String screenResults = "";
        private String screenResultsDir = "";
        private Integer detailLimit = 0;
        private String onRisk = "";
        private AiFile ai = new AiFile();
        private String greeting = "";
        private BlacklistFile blacklist = new BlacklistFile();
        private Map<String, Map<String, String>> codes = new LinkedHashMap<>();
        private RulesFile rules = new RulesFile();
        private String candidateProfile = "";
        private PromptsFile prompts = new PromptsFile();
    }

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class AiFile {
        private String baseUrl = "";
        private String apiKey = "";
        private String model = "";
    }

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RulesFile {
        private List<String> companyTokens = new ArrayList<>();
        private List<String> jobTitleTokens = new ArrayList<>();
    }

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class PromptsFile {
        private String title = "";
        private String jd = "";
    }

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class BlacklistFile {
        private List<String> companies = new ArrayList<>();
        private List<String> jobs = new ArrayList<>();
        private List<String> recruiters = new ArrayList<>();
    }
}
