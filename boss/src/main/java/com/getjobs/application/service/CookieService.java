package com.getjobs.application.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/** 登录态在 Chrome browser-data。 */
@Slf4j
@Service
public class CookieService {

    public boolean saveOrUpdateCookie(String platform, String cookieValue, String remark) {
        return true;
    }

    public boolean clearCookieByPlatform(String platform, String remark) {
        return true;
    }
}
