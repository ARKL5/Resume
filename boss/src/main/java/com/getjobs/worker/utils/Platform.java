package com.getjobs.worker.utils;

import lombok.Getter;

@Getter
public enum Platform {
    BOSS("Boss直聘");

    private final String platformName;

    Platform(String platformName) {
        this.platformName = platformName;
    }
}
