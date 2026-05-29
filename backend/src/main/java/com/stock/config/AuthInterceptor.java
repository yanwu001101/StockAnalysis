package com.stock.config;

import io.jsonwebtoken.Claims;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class AuthInterceptor implements HandlerInterceptor {

    private final JwtConfig jwtConfig;

    public AuthInterceptor(JwtConfig jwtConfig) {
        this.jwtConfig = jwtConfig;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        // Allow OPTIONS requests for CORS
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        String path = request.getRequestURI();
        String role = null;

        String token = request.getHeader("Authorization");
        if (token != null && token.startsWith("Bearer ")) {
            token = token.substring(7);
            if (jwtConfig.validateToken(token)) {
                Claims claims = jwtConfig.parseToken(token);
                request.setAttribute("userId", claims.get("userId", Long.class));
                request.setAttribute("username", claims.getSubject());
                role = claims.get("role", String.class);
                if (role == null) role = "USER";
                request.setAttribute("role", role);
            }
        }

        // /api/admin/** must be ADMIN — anonymous or non-admin gets 403/401
        if (path.startsWith("/api/admin/")) {
            if (role == null) {
                response.setStatus(401);
                return false;
            }
            if (!"ADMIN".equals(role)) {
                response.setStatus(403);
                return false;
            }
            return true;
        }

        if (role != null) return true;

        // Public endpoints (no token required) — keep the C-side surface usable
        // for anonymous market browsing, but admin is no longer in this list.
        if (path.startsWith("/api/user/login") || path.startsWith("/api/user/register") ||
            path.startsWith("/api/market") || path.startsWith("/api/stock") ||
            path.startsWith("/api/screen") || path.startsWith("/api/strategies") ||
            path.startsWith("/api/strategy-tops") ||
            path.startsWith("/api/backtest") || path.startsWith("/api/lhb") ||
            path.startsWith("/api/moneyflow") || path.startsWith("/api/condition-fields") ||
            path.startsWith("/api/expression")) {
            return true;
        }

        response.setStatus(401);
        return false;
    }
}
