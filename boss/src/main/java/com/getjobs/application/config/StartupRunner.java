package com.getjobs.application.config;

import com.getjobs.worker.manager.PlaywrightManager;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * 启动后只拉起 Boss 浏览器，不再打开原配置 UI。
 */
@Slf4j
@Component
public class StartupRunner implements ApplicationRunner {

    private final PlaywrightManager playwrightManager;

    public StartupRunner(PlaywrightManager playwrightManager) {
        this.playwrightManager = playwrightManager;
    }

    @Override
    public void run(ApplicationArguments args) {
        try {
            playwrightManager.init();
        } catch (Exception e) {
            log.error("Playwright 初始化失败: {}", e.getMessage());
            throw e;
        }
    }
}
