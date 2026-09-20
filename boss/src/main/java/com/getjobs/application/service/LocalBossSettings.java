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
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 本机运行配置：只读 boss.yaml。已开聊记录仍是 opened-chats.jsonl。
 */
@Slf4j
@Service
public class LocalBossSettings {

    private static final Path SEARCH = Path.of("boss.yaml");
    private static final Path OPENED = Path.of("opened-chats.jsonl");

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

    public Path screenResultsPath() {
        String raw = loadSearch().getScreenResults();
        if (raw == null || raw.isBlank()) {
            throw new IllegalStateException("boss.yaml 的 screenResults 不能为空");
        }
        Path path = Path.of(raw.trim());
        if (!path.isAbsolute()) {
            path = Path.of(System.getProperty("user.dir", ".")).resolve(path).normalize();
        }
        return path;
    }

    public int detailLimit() {
        Integer n = loadSearch().getDetailLimit();
        if (n == null || n < 0) {
            return 0;
        }
        return n;
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
        private Integer detailLimit = 0;
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
