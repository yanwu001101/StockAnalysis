package com.stock.service;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.exception.BusinessException;
import com.stock.mapper.AiAnalysisRunMapper;
import com.stock.mapper.UserAiConfigMapper;
import com.stock.model.entity.AiAnalysisRun;
import com.stock.model.entity.UserAiConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.*;

@Service
public class AiAnalysisService {

    private static final SecureRandom RNG = new SecureRandom();

    private final UserAiConfigMapper configMapper;
    private final AiAnalysisRunMapper runMapper;
    private final PortfolioService portfolioService;
    private final RestTemplate restTemplate;
    private final byte[] aesKey;

    public AiAnalysisService(UserAiConfigMapper configMapper,
                             AiAnalysisRunMapper runMapper,
                             PortfolioService portfolioService,
                             RestTemplate restTemplate,
                             @Value("${jwt.secret}") String secret) {
        this.configMapper = configMapper;
        this.runMapper = runMapper;
        this.portfolioService = portfolioService;
        this.restTemplate = restTemplate;
        this.aesKey = sha256(secret == null ? "stock-analysis" : secret);
    }

    public Map<String, Object> presets() {
        List<Map<String, Object>> items = List.of(
            preset("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
            preset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
            preset("moonshot", "Moonshot / Kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
            preset("qwen", "通义千问兼容模式", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
            preset("zhipu", "智谱 GLM 兼容模式", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash")
        );
        return Map.of("items", items);
    }

    public Map<String, Object> getConfig(Long userId) {
        UserAiConfig cfg = findConfig(userId);
        if (cfg == null) {
            return Map.of(
                "configured", false,
                "enabled", false,
                "provider", "deepseek",
                "baseUrl", "https://api.deepseek.com/v1",
                "model", "deepseek-chat",
                "temperature", 0.2
            );
        }
        return viewConfig(cfg);
    }

    public Map<String, Object> saveConfig(Long userId, Map<String, Object> body) {
        String baseUrl = string(body.get("baseUrl"));
        String model = string(body.get("model"));
        if (baseUrl.isEmpty()) throw new BusinessException("缺少 base URL");
        if (model.isEmpty()) throw new BusinessException("缺少模型名称");

        UserAiConfig cfg = findConfig(userId);
        if (cfg == null) {
            cfg = new UserAiConfig();
            cfg.setUserId(userId);
        }
        cfg.setProvider(stringOr(body.get("provider"), "openai-compatible"));
        cfg.setBaseUrl(baseUrl);
        cfg.setModel(model);
        cfg.setTemperature(decimal(body.get("temperature"), new BigDecimal("0.20")));
        cfg.setEnabled(Boolean.FALSE.equals(body.get("enabled")) ? 0 : 1);

        String apiKey = string(body.get("apiKey"));
        if (!apiKey.isEmpty()) {
            cfg.setApiKeyCipher(encrypt(apiKey));
            cfg.setApiKeyMask(mask(apiKey));
        } else if (cfg.getApiKeyCipher() == null || cfg.getApiKeyCipher().isEmpty()) {
            throw new BusinessException("首次配置需要填写 API Key");
        }

        if (cfg.getId() == null) configMapper.insert(cfg);
        else configMapper.updateById(cfg);
        return viewConfig(cfg);
    }

    public Map<String, Object> testConfig(Long userId) {
        UserAiConfig cfg = requireEnabledConfig(userId);
        String text = chat(cfg, List.of(
            message("system", "你是一个简洁的连接测试助手。"),
            message("user", "请只回复：连接成功")
        ));
        return Map.of("ok", true, "reply", text, "model", cfg.getModel());
    }

    public Map<String, Object> analyzePortfolio(Long userId, Map<String, Object> body) {
        UserAiConfig cfg = requireEnabledConfig(userId);
        BigDecimal cash = decimal(body.get("cash"), BigDecimal.ZERO);
        String question = stringOr(body.get("question"), "请分析我的持仓，并给出适合小白执行的买入、卖出、做T和风险控制建议。");
        Map<String, Object> advice = portfolioService.advice(userId, cash);
        String preference = preferenceSummary(userId);

        JSONObject payload = new JSONObject();
        payload.put("portfolio", advice);
        payload.put("question", question);
        payload.put("preferenceMemory", preference);

        String system = """
            你是一个A股持仓分析助手。你只能提供辅助决策和风险提示，不能承诺收益，不能要求用户输入交易密码。
            输出要面向新手，必须清楚说明：现在要不要买、要不要卖、是否适合做T、每一步怎么做、哪些条件下要改变计划。
            如果数据不足，要明确说明缺口。不要编造账户、成交或实时数据。
            """;
        String user = "以下是系统整理的持仓、规则建议和用户问题，请给出中文分析。要求分为：总体判断、逐股操作、做T计划、风险线、明天/下个交易日观察点。\n"
            + payload.toJSONString();

        String result = chat(cfg, List.of(message("system", system), message("user", user)));

        AiAnalysisRun run = new AiAnalysisRun();
        run.setUserId(userId);
        run.setScope("portfolio");
        run.setRequestJson(payload.toJSONString());
        run.setResultText(result);
        run.setModel(cfg.getModel());
        runMapper.insert(run);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", run.getId());
        out.put("model", cfg.getModel());
        out.put("content", result);
        out.put("portfolio", advice);
        return out;
    }

    public List<Map<String, Object>> history(Long userId) {
        List<AiAnalysisRun> rows = runMapper.selectList(new LambdaQueryWrapper<AiAnalysisRun>()
            .eq(AiAnalysisRun::getUserId, userId)
            .orderByDesc(AiAnalysisRun::getCreatedAt)
            .last("LIMIT 20"));
        List<Map<String, Object>> out = new ArrayList<>();
        for (AiAnalysisRun r : rows) {
            out.add(Map.of(
                "id", r.getId(),
                "scope", r.getScope(),
                "model", r.getModel(),
                "content", r.getResultText(),
                "feedback", r.getFeedback() == null ? "" : r.getFeedback(),
                "feedbackNote", r.getFeedbackNote() == null ? "" : r.getFeedbackNote(),
                "createdAt", r.getCreatedAt()
            ));
        }
        return out;
    }

    public Map<String, Object> feedback(Long userId, Long id, Map<String, Object> body) {
        AiAnalysisRun run = runMapper.selectOne(new LambdaQueryWrapper<AiAnalysisRun>()
            .eq(AiAnalysisRun::getId, id)
            .eq(AiAnalysisRun::getUserId, userId));
        if (run == null) throw new BusinessException(404, "分析记录不存在");
        run.setFeedback(stringOr(body.get("feedback"), ""));
        run.setFeedbackNote(string(body.get("note")));
        runMapper.updateById(run);
        return Map.of("id", id, "saved", true);
    }

    private String chat(UserAiConfig cfg, List<JSONObject> messages) {
        String apiKey = decrypt(cfg.getApiKeyCipher());
        JSONObject req = new JSONObject();
        req.put("model", cfg.getModel());
        req.put("messages", messages);
        req.put("temperature", cfg.getTemperature() == null ? 0.2 : cfg.getTemperature().doubleValue());
        req.put("stream", false);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth(apiKey);
        ResponseEntity<String> resp = restTemplate.exchange(
            chatUrl(cfg.getBaseUrl()),
            HttpMethod.POST,
            new HttpEntity<>(req.toJSONString(), headers),
            String.class
        );
        JSONObject obj = JSONObject.parseObject(resp.getBody());
        JSONArray choices = obj == null ? null : obj.getJSONArray("choices");
        if (choices == null || choices.isEmpty()) throw new BusinessException("模型没有返回有效内容");
        JSONObject msg = choices.getJSONObject(0).getJSONObject("message");
        String content = msg == null ? "" : msg.getString("content");
        if (content == null || content.isBlank()) throw new BusinessException("模型返回内容为空");
        return content.trim();
    }

    private UserAiConfig findConfig(Long userId) {
        return configMapper.selectOne(new LambdaQueryWrapper<UserAiConfig>().eq(UserAiConfig::getUserId, userId));
    }

    private UserAiConfig requireEnabledConfig(Long userId) {
        UserAiConfig cfg = findConfig(userId);
        if (cfg == null || cfg.getEnabled() == null || cfg.getEnabled() == 0) {
            throw new BusinessException("请先在 AI 设置里配置并启用模型 API Key");
        }
        if (cfg.getApiKeyCipher() == null || cfg.getApiKeyCipher().isEmpty()) {
            throw new BusinessException("当前 AI 配置缺少 API Key");
        }
        return cfg;
    }

    private String preferenceSummary(Long userId) {
        List<AiAnalysisRun> rows = runMapper.selectList(new LambdaQueryWrapper<AiAnalysisRun>()
            .eq(AiAnalysisRun::getUserId, userId)
            .ne(AiAnalysisRun::getFeedback, "")
            .orderByDesc(AiAnalysisRun::getCreatedAt)
            .last("LIMIT 8"));
        if (rows.isEmpty()) return "暂无反馈记忆。";
        StringBuilder sb = new StringBuilder("用户历史反馈偏好：");
        for (AiAnalysisRun r : rows) {
            sb.append("\n- ").append(r.getFeedback()).append(": ").append(r.getFeedbackNote());
        }
        return sb.toString();
    }

    private Map<String, Object> viewConfig(UserAiConfig cfg) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("configured", cfg.getApiKeyCipher() != null && !cfg.getApiKeyCipher().isEmpty());
        out.put("enabled", cfg.getEnabled() != null && cfg.getEnabled() == 1);
        out.put("provider", cfg.getProvider());
        out.put("baseUrl", cfg.getBaseUrl());
        out.put("model", cfg.getModel());
        out.put("apiKeyMask", cfg.getApiKeyMask());
        out.put("temperature", cfg.getTemperature());
        out.put("updatedAt", cfg.getUpdatedAt());
        return out;
    }

    private Map<String, Object> preset(String id, String name, String baseUrl, String model) {
        return Map.of("id", id, "name", name, "baseUrl", baseUrl, "model", model);
    }

    private JSONObject message(String role, String content) {
        JSONObject o = new JSONObject();
        o.put("role", role);
        o.put("content", content);
        return o;
    }

    private String chatUrl(String baseUrl) {
        String url = string(baseUrl);
        while (url.endsWith("/")) url = url.substring(0, url.length() - 1);
        if (url.endsWith("/chat/completions")) return url;
        return url + "/chat/completions";
    }

    private String encrypt(String plain) {
        try {
            byte[] iv = new byte[12];
            RNG.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new GCMParameterSpec(128, iv));
            byte[] enc = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(iv) + "." + Base64.getEncoder().encodeToString(enc);
        } catch (Exception e) {
            throw new BusinessException("API Key 加密失败");
        }
    }

    private String decrypt(String cipherText) {
        try {
            String[] parts = cipherText.split("\\.", 2);
            byte[] iv = Base64.getDecoder().decode(parts[0]);
            byte[] enc = Base64.getDecoder().decode(parts[1]);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new GCMParameterSpec(128, iv));
            return new String(cipher.doFinal(enc), StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new BusinessException("API Key 解密失败，请重新保存 AI 配置");
        }
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private String mask(String key) {
        if (key.length() <= 8) return "****";
        return key.substring(0, 4) + "..." + key.substring(key.length() - 4);
    }

    private static String string(Object value) {
        return value == null ? "" : value.toString().trim();
    }

    private static String stringOr(Object value, String fallback) {
        String s = string(value);
        return s.isEmpty() ? fallback : s;
    }

    private static BigDecimal decimal(Object value, BigDecimal fallback) {
        if (value == null) return fallback;
        try { return new BigDecimal(value.toString()); } catch (Exception e) { return fallback; }
    }
}
