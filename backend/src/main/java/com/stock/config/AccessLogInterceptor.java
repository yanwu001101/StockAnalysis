package com.stock.config;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * Access log + slow-request warning.
 *
 * Logs every request at INFO. Requests slower than {@link #SLOW_THRESHOLD_MS}
 * get bumped to WARN so they stand out in the operator's grep.
 */
@Component
public class AccessLogInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger("ACCESS");
    private static final String START_KEY = "_accesslog_start";
    private static final long SLOW_THRESHOLD_MS = 1000;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        request.setAttribute(START_KEY, System.currentTimeMillis());
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        Object start = request.getAttribute(START_KEY);
        if (!(start instanceof Long s)) return;
        long elapsed = System.currentTimeMillis() - s;
        int status = response.getStatus();
        String method = request.getMethod();
        String uri = request.getRequestURI();
        String query = request.getQueryString();
        String line = query == null
                ? String.format("%s %s -> %d in %dms", method, uri, status, elapsed)
                : String.format("%s %s?%s -> %d in %dms", method, uri, query, status, elapsed);
        if (elapsed >= SLOW_THRESHOLD_MS) {
            log.warn("SLOW {}", line);
        } else if (status >= 500) {
            log.warn("{}", line);
        } else {
            log.info("{}", line);
        }
    }
}
