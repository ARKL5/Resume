package com.getjobs.application.service;

import com.getjobs.worker.boss.BossConfig;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
@RequiredArgsConstructor
public class ConfigService {
    private final LocalBossSettings localBossSettings;
    private final BossService bossService;

    public Map<String, String> getAiConfigs() {
        return localBossSettings.aiConfigs();
    }

    public BossConfig getBossConfig() {
        return bossService.loadBossConfig();
    }
}
