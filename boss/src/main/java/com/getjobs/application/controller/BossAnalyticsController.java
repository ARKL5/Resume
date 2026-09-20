package com.getjobs.application.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@CrossOrigin(origins = "*")
@RequestMapping("/api/boss")
public class BossAnalyticsController {

    private final com.getjobs.application.service.LocalBossSettings localBossSettings;

    public BossAnalyticsController(com.getjobs.application.service.LocalBossSettings localBossSettings) {
        this.localBossSettings = localBossSettings;
    }

    @GetMapping("/opened-chats")
    public Map<String, Object> openedChats() {
        return Map.of("encryptIds", List.copyOf(localBossSettings.openedEncryptIds()));
    }

    /**
     * 对照页：一岗一行，只读当前 jsonl。
     */
    @GetMapping("/screen-results")
    public Map<String, Object> screenResults() {
        Path log = localBossSettings.screenResultsPath();
        List<Map<String, Object>> items = new ArrayList<>();
        if (Files.exists(log)) {
            try {
                ObjectMapper mapper = new ObjectMapper();
                for (String line : Files.readAllLines(log, StandardCharsets.UTF_8)) {
                    if (line == null || line.isBlank()) {
                        continue;
                    }
                    try {
                        @SuppressWarnings("unchecked")
                        Map<String, Object> row = mapper.readValue(line, Map.class);
                        if (isPlacedRow(row)) {
                            items.add(row);
                        }
                    } catch (Exception ignore) {
                    }
                }
            } catch (Exception e) {
                return Map.of("items", List.of(), "error", e.getMessage());
            }
        }
        return Map.of("items", items);
    }

    private static boolean isPlacedRow(Map<String, Object> row) {
        if (row == null) {
            return false;
        }
        Object stage = row.get("stage");
        Object city = row.get("cityPage");
        if (stage == null || city == null) {
            return false;
        }
        String s = String.valueOf(stage).trim();
        String c = String.valueOf(city).trim();
        return switch (s) {
            case "rule_drop", "ai_title_drop", "ai_title_pending", "ai_jd_drop",
                 "jd_wait", "jd_wait_other", "ai_jd_pending", "ai_keep" ->
                    "杭州".equals(c) || "上海".equals(c) || "其它".equals(c);
            default -> false;
        };
    }
}
