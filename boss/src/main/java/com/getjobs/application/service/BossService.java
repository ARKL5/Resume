package com.getjobs.application.service;

import com.getjobs.worker.boss.BossConfig;
import com.getjobs.worker.utils.Constant;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

@Service
@Slf4j
@RequiredArgsConstructor
public class BossService {

    private final LocalBossSettings localBossSettings;

    public BossConfig loadBossConfig() {
        LocalBossSettings.SearchFile file = localBossSettings.loadSearch();
        BossConfig config = new BossConfig();
        config.setSayHi(localBossSettings.loadGreeting());
        config.setDebugger(false);
        config.setEnableAI(false);
        config.setFilterDeadHR(true);
        config.setSendImgResume(Boolean.TRUE.equals(file.getSendImgResume()));
        config.setWaitTime(file.getWaitTime() != null ? String.valueOf(file.getWaitTime()) : "18");
        config.setDetailLimit(file.getDetailLimit() == null ? 0 : Math.max(0, file.getDetailLimit()));
        config.setKeywordGapSeconds(file.getKeywordGapSeconds() == null ? 300 : Math.max(0, file.getKeywordGapSeconds()));
        config.setKeywords(nonNullList(file.getKeywords()));
        config.setCityCode(toCodes("city", nonNullList(file.getCities())));
        config.setIndustry(toCodes("industry", nonNullList(file.getIndustry())));
        config.setExperience(toCodes("experience", nonNullList(file.getExperience())));
        config.setDegree(toCodes("degree", nonNullList(file.getDegree())));
        config.setScale(toCodes("scale", nonNullList(file.getScale())));
        config.setStage(toCodes("stage", nonNullList(file.getStage())));
        config.setSalary(toCodes("salary", nonNullList(file.getSalary())));

        List<String> jobTypeCodes = toCodes("jobType",
                file.getJobType() == null || file.getJobType().isBlank()
                        ? List.of()
                        : List.of(file.getJobType()));
        config.setJobType(jobTypeCodes.isEmpty() ? Constant.UNLIMITED_CODE : jobTypeCodes.get(0));
        config.setDeadStatus(List.of("未上线"));

        if (config.getKeywords().isEmpty()) {
            throw new IllegalStateException("boss.yaml 的 keywords 不能为空");
        }
        if (config.getCityCode().isEmpty()) {
            throw new IllegalStateException("boss.yaml 的 cities 不能为空，且须能对应 codes.city");
        }
        log.info("已从 boss.yaml 加载 Boss 配置");
        return config;
    }

    public List<String> toCodes(String type, List<String> items) {
        if (items == null || items.isEmpty()) {
            return List.of();
        }
        List<String> codes = new ArrayList<>();
        for (String raw : items) {
            if (raw == null || raw.isBlank()) {
                continue;
            }
            codes.add(localBossSettings.codeOf(type, raw.trim()));
        }
        return codes;
    }

    public Set<String> getBlackCompanies() {
        return setOf(localBossSettings.loadBlacklist().getCompanies());
    }

    public Set<String> getBlackRecruiters() {
        return setOf(localBossSettings.loadBlacklist().getRecruiters());
    }

    public Set<String> getBlackJobs() {
        return setOf(localBossSettings.loadBlacklist().getJobs());
    }

    public boolean addBlacklist(String type, String value) {
        localBossSettings.addToBlacklist(type, value);
        return true;
    }

    private static List<String> nonNullList(List<String> list) {
        return list == null ? List.of() : list;
    }

    private static Set<String> setOf(List<String> list) {
        return list == null ? Set.of() : new java.util.LinkedHashSet<>(list);
    }
}
