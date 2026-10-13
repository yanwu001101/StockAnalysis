package com.stock.service;

import com.stock.exception.BusinessException;
import org.springframework.http.HttpHeaders;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;

/** Signs gateway-established identities, never a user-supplied owner header. */
public final class ResearchJobAuth {
    public static final String OWNER_HEADER = "X-Research-Owner";
    public static final String TIME_HEADER = "X-Research-Timestamp";
    public static final String SIGNATURE_HEADER = "X-Research-Signature";
    public static final int MAX_BODY_BYTES = 256 * 1024;
    private static final String DOMAIN = "research-jobs-v1";
    private static final String PUBLIC_DEFAULT = "StockScreenerSecretKey2024MustBe256BitsLong!!";
    private static final String CONFIG_ERROR = "研究任务鉴权未配置：两端 JWT_SECRET 必须相同、至少 32 字节且不是公共默认值";

    private ResearchJobAuth() {}

    public static String signature(String secret, long owner, long timestamp, String method, String path, byte[] body) {
        if (owner <= 0) throw new BusinessException(401, "未登录");
        if (secret == null || secret.isBlank() || PUBLIC_DEFAULT.equals(secret.strip())
                || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new BusinessException(503, CONFIG_ERROR);
        }
        if (body.length > MAX_BODY_BYTES) throw new BusinessException(413, "研究任务请求体过大");
        try {
            byte[] key = hmac(secret.getBytes(StandardCharsets.UTF_8), DOMAIN.getBytes(StandardCharsets.UTF_8));
            String bodyHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
            String canonical = owner + "\n" + timestamp + "\n" + method.toUpperCase(Locale.ROOT)
                    + "\n" + path + "\n" + bodyHash;
            return HexFormat.of().formatHex(hmac(key, canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException error) {
            throw new BusinessException(503, "研究任务签名服务暂不可用");
        }
    }

    public static HttpHeaders headers(String secret, long owner, long timestamp, String method, String path, byte[] body) {
        String signature = signature(secret, owner, timestamp, method, path, body);
        HttpHeaders headers = new HttpHeaders();
        headers.set(OWNER_HEADER, Long.toString(owner));
        headers.set(TIME_HEADER, Long.toString(timestamp));
        headers.set(SIGNATURE_HEADER, signature);
        return headers;
    }

    private static byte[] hmac(byte[] key, byte[] data) throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(data);
    }
}
