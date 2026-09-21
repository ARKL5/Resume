package com.getjobs.application.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.ResponseEntity;
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
     * 对照页可切换的筛选结果列表。只读。
     */
    @GetMapping("/screen-files")
    public Map<String, Object> screenFiles() {
        Path cur = localBossSettings.currentScreenFile();
        return Map.of(
                "files", localBossSettings.listScreenFiles(),
                "current", cur == null ? "" : cur.getFileName().toString()
        );
    }

    /**
     * 对照页：一岗一行。file 缺省则读正在写的那份，否则读点名的 jsonl。
     */
    @GetMapping("/screen-results")
    public ResponseEntity<Map<String, Object>> screenResults(
            @RequestParam(value = "file", required = false) String file) {
        Path log;
        try {
            if (file != null && !file.isBlank()) {
                log = localBossSettings.resolveListedFile(file.trim());
            } else {
                log = localBossSettings.screenResultsPath();
            }
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "items", List.of(),
                    "file", file == null ? "" : file,
                    "error", e.getMessage()));
        } catch (IllegalStateException e) {
            return ResponseEntity.ok(Map.of("items", List.of(), "file", ""));
        }
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
                return ResponseEntity.ok(Map.of(
                        "items", List.of(),
                        "file", log.getFileName().toString(),
                        "error", e.getMessage()));
            }
        }
        return ResponseEntity.ok(Map.of("items", items, "file", log.getFileName().toString()));
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
