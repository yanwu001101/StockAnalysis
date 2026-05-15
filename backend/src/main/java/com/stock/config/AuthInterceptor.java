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

        String token = request.getHeader("Authorization");
        if (token != null && token.startsWith("Bearer ")) {
            token = token.substring(7);
            if (jwtConfig.validateToken(token)) {
                Claims claims = jwtConfig.parseToken(token);
                request.setAttribute("userId", claims.get("userId", Long.class));
                request.setAttribute("username", claims.getSubject());
                return true;
            }
        }

        // For non-critical endpoints, allow without auth
        String path = request.getRequestURI();
        if (path.startsWith("/api/user/login") || path.startsWith("/api/user/register") ||
            path.startsWith("/api/market") || path.startsWith("/api/stock") ||
            path.startsWith("/api/screen") || path.startsWith("/api/strategies") ||
            path.startsWith("/api/backtest")) {
            return true;
        }

        response.setStatus(401);
        return false;
    }
}
