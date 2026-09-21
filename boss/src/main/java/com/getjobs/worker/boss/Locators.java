package com.getjobs.worker.boss;

/**
 * 筛选实际用到的定位器。开聊路径用内联选择器。
 */
public class Locators {
    public static final String JOB_LIST_SELECTOR = "ul.rec-job-list li.job-card-box";
    public static final String HR_ACTIVE_TIME = "//span[@class='boss-active-time']";
    public static final String LOGIN_BTNS = "//div[@class='btns']";
    public static final String PAGE_HEADER = "//h1";
    public static final String ERROR_PAGE_LOGIN = "//a[@ka='403_login']";
}
