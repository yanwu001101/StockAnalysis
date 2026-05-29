package com.stock.config;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.time.LocalDateTime;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

/**
 * Access log + slow-request warning.
 *
 * Logs every request at INFO. Requests slower than {@link #SLOW_THRESHOLD_MS}
 * get bumped to WARN so they stand out in the operator's grep.
 *
 * Keeps the most recent N entries in a static ring buffer so the admin
 * monitor page can render them without grepping container logs.
 */
@Component
public class AccessLogInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger("ACCESS");
    private static final String START_KEY = "_accesslog_start";
    private static final long SLOW_THRESHOLD_MS = 1000;
    private static final int BUFFER_SIZE = 500;

    private static final Deque<Entry> BUFFER = new ArrayDeque<>(BUFFER_SIZE);
    private static final Object BUFFER_LOCK = new Object();

    public record Entry(LocalDateTime ts, String method, String uri, String query,
                         int status, long elapsedMs, String ip) {}

    public static List<Entry> snapshot(int limit) {
        synchronized (BUFFER_LOCK) {
            int n = Math.min(limit > 0 ? limit : BUFFER.size(), BUFFER.size());
            List<Entry> out = new ArrayList<>(n);
            int skip = BUFFER.size() - n;
            int i = 0;
            for (Entry e : BUFFER) {
                if (i++ < skip) continue;
                out.add(e);
            }
            // newest first
            java.util.Collections.reverse(out);
            return out;
        }
    }

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
        String ip = clientIp(request);

        Entry e = new Entry(LocalDateTime.now(), method, uri, query, status, elapsed, ip);
        synchronized (BUFFER_LOCK) {
            if (BUFFER.size() >= BUFFER_SIZE) BUFFER.pollFirst();
            BUFFER.addLast(e);
        }

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

    private static String clientIp(HttpServletRequest req) {
        String xf = req.getHeader("X-Forwarded-For");
        if (xf != null && !xf.isBlank()) return xf.split(",")[0].trim();
        String real = req.getHeader("X-Real-IP");
        if (real != null && !real.isBlank()) return real;
        return req.getRemoteAddr();
    }
}
