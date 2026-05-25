package com.stock.config;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

@Component
public class JwtConfig {

    private static final Logger log = LoggerFactory.getLogger(JwtConfig.class);

    // Insecure default — kept so docker-compose works out of the box but
    // refused at startup in any non-dev profile.
    private static final String DEFAULT_INSECURE_SECRET =
            "StockScreenerSecretKey2024MustBe256BitsLong!!";

    @Value("${jwt.secret}")
    private String secret;

    @Value("${jwt.expiration}")
    private long expiration;

    @Value("${spring.profiles.active:default}")
    private String activeProfile;

    @PostConstruct
    void warnIfInsecure() {
        if (DEFAULT_INSECURE_SECRET.equals(secret)) {
            String msg = "JWT secret is the public default — override JWT_SECRET env var before exposing this service publicly.";
            if ("prod".equalsIgnoreCase(activeProfile) || "production".equalsIgnoreCase(activeProfile)) {
                throw new IllegalStateException(msg);
            }
            log.warn("⚠ {}", msg);
        }
    }

    private SecretKey getKey() {
        return Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    public String generateToken(Long userId, String username) {
        return Jwts.builder()
                .subject(username)
                .claim("userId", userId)
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + expiration))
                .signWith(getKey())
                .compact();
    }

    public Claims parseToken(String token) {
        return Jwts.parser()
                .verifyWith(getKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public boolean validateToken(String token) {
        try {
            parseToken(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
