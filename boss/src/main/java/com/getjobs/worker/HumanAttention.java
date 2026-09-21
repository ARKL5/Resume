package com.getjobs.worker;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.awt.Toolkit;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 人机验证、登录失效、详情读空时提醒本人。onRisk=wait 时暂停；onRisk=stop 时结束本轮。
 */
@Slf4j
@Component
public class HumanAttention {
    private final AtomicReference<String> reason = new AtomicReference<>();
    private final AtomicLong sinceMs = new AtomicLong(0);
    private final java.util.concurrent.atomic.AtomicBoolean resume = new java.util.concurrent.atomic.AtomicBoolean(false);

    public void raise(String message) {
        reason.set(message);
        sinceMs.compareAndSet(0, System.currentTimeMillis());
        log.warn("需要人工：{}", message);
    }

    public void clear() {
        reason.set(null);
        sinceMs.set(0);
        resume.set(false);
    }

    public void requestResume() {
        resume.set(true);
        reason.set(null);
        sinceMs.set(0);
        log.info("人工确认已处理，恢复筛选");
    }

    public boolean consumeResume() {
        return resume.compareAndSet(true, false);
    }

    public boolean isRaised() {
        return reason.get() != null;
    }

    public Map<String, Object> snapshot() {
        String r = reason.get();
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("needHuman", r != null);
        m.put("needHumanReason", r == null ? "" : r);
        m.put("needHumanSince", sinceMs.get());
        return m;
    }

    public void notifyDesktop(String message) {
        try {
            Toolkit.getDefaultToolkit().beep();
        } catch (Exception ignore) {
        }
        Path script = Path.of("scripts", "notify-human.ps1");
        if (!Files.exists(script)) {
            return;
        }
        try {
            new ProcessBuilder(
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", script.toAbsolutePath().toString(),
                    "-Message", message
            ).start();
        } catch (Exception e) {
            log.warn("桌面提醒失败：{}", e.getMessage());
        }
    }
}
