package com.stock.service;

import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.exception.BusinessException;
import com.stock.mapper.AiChatMessageMapper;
import com.stock.mapper.AiChatSessionMapper;
import com.stock.model.entity.AiChatMessage;
import com.stock.model.entity.AiChatSession;
import com.stock.model.entity.UserAiConfig;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * AI 多轮对话：专业金融理财师人设 + 会话持久化 + 懒加载持仓上下文。
 *
 * 复用 AiAnalysisService 的 OpenAI 兼容客户端（chat/message）、密钥解密、
 * 配置校验与用户偏好记忆——本类只补齐「多轮」与「人设」：
 *   * 会话历史直接映射为 messages 数组（最近 40 条）；
 *   * 持仓上下文懒加载：仅当用户问题涉及持仓/买卖/仓位等关键词，或会话首轮
 *     时才组装，避免每轮都触发逐股的 data-service 调用。
 */
@Service
public class AiChatService {

    private static final Set<String> CONTEXT_KEYWORDS = Set.of(
            "持仓", "仓位", "账户", "我的股", "该买", "该卖", "买入", "卖出", "止盈",
            "止损", "加仓", "减仓", "市值", "盈亏", "做T", "做 T", "套牢", "配置", "建仓", "清仓");

    private static final String PERSONA = """
            你是「智投顾问」，一名严谨的专业金融理财师（A 股方向），服务对象是个人投资者，通过对话给出分析与建议。
            表达要求：先给结论，再给理由；分点结构化；语言专业但通俗，不堆砌术语；单条回答控制在 400 字以内，除非用户要求展开。
            合规红线：只能提供辅助决策与风险提示，不承诺收益，不使用"稳赚、必涨、保本"等措辞；不代客操作，不索要账号、密码、验证码；
            不编造实时行情、财报数字或成交数据——需要最新数据时，明确告诉用户去平台哪个页面查看（如「盘面」「研究→因子检验」「自选」）。
            内容要求：涉及具体标的或操作建议时，必须同时说明风险与"什么情况下不应该这么做"；在合适的时机提醒"以上为分析参考，不构成投资建议"。
            区分事实与观点；用户提供的持仓与反馈记忆若已在上下文中，优先基于它回答；信息不足时先列出还缺什么，再给一般性框架。
            """;

    private final AiAnalysisService ai;
    private final PortfolioService portfolioService;
    private final AiChatSessionMapper sessionMapper;
    private final AiChatMessageMapper messageMapper;

    public AiChatService(AiAnalysisService ai,
                         PortfolioService portfolioService,
                         AiChatSessionMapper sessionMapper,
                         AiChatMessageMapper messageMapper) {
        this.ai = ai;
        this.portfolioService = portfolioService;
        this.sessionMapper = sessionMapper;
        this.messageMapper = messageMapper;
    }

    public Map<String, Object> chat(Long userId, Long sessionId, String userMessage) {
        if (userMessage == null || userMessage.isBlank()) throw new BusinessException("消息不能为空");
        String content = userMessage.trim();
        if (content.length() > 4000) content = content.substring(0, 4000);

        UserAiConfig cfg = ai.requireEnabledConfig(userId);
        AiChatSession session = resolveSession(userId, sessionId, content);

        List<AiChatMessage> history = messageMapper.selectList(new LambdaQueryWrapper<AiChatMessage>()
                .eq(AiChatMessage::getSessionId, session.getId())
                .orderByAsc(AiChatMessage::getId)
                .last("LIMIT 40"));

        List<JSONObject> messages = new ArrayList<>();
        messages.add(ai.message("system", PERSONA + "\n" + ai.preferenceSummary(userId)));
        for (AiChatMessage m : history) {
            messages.add(ai.message(m.getRole(), m.getContent()));
        }
        // 懒加载持仓上下文：首轮（有持仓时）或问题涉及时注入，不每轮重复组装
        boolean firstTurn = history.isEmpty();
        if (firstTurn || mentionsContext(content)) {
            String ctx = portfolioContext(userId);
            if (ctx != null) {
                messages.add(ai.message("system",
                        "以下是系统整理的用户最新持仓快照（自动注入，仅在与问题相关时使用，不要复述全文）：\n" + ctx));
            }
        }
        messages.add(ai.message("user", content));

        String reply = ai.chat(cfg, messages);

        AiChatMessage um = new AiChatMessage();
        um.setSessionId(session.getId());
        um.setUserId(userId);
        um.setRole("user");
        um.setContent(content);
        messageMapper.insert(um);
        AiChatMessage am = new AiChatMessage();
        am.setSessionId(session.getId());
        am.setUserId(userId);
        am.setRole("assistant");
        am.setContent(reply);
        messageMapper.insert(am);

        if (session.getTitle() == null || session.getTitle().isBlank() || "新对话".equals(session.getTitle())) {
            session.setTitle(content.length() > 24 ? content.substring(0, 24) + "…" : content);
        }
        sessionMapper.updateById(session);   // updated_at 由 ON UPDATE 刷新

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("sessionId", session.getId());
        out.put("title", session.getTitle());
        out.put("reply", reply);
        out.put("model", cfg.getModel());
        return out;
    }

    public List<Map<String, Object>> sessions(Long userId) {
        List<AiChatSession> rows = sessionMapper.selectList(new LambdaQueryWrapper<AiChatSession>()
                .eq(AiChatSession::getUserId, userId)
                .orderByDesc(AiChatSession::getUpdatedAt)
                .last("LIMIT 30"));
        List<Map<String, Object>> out = new ArrayList<>();
        for (AiChatSession s : rows) {
            out.add(Map.of("id", s.getId(), "title", s.getTitle(), "updatedAt", s.getUpdatedAt()));
        }
        return out;
    }

    public List<Map<String, Object>> messages(Long userId, Long sessionId) {
        AiChatSession session = ownedSession(userId, sessionId);
        List<AiChatMessage> rows = messageMapper.selectList(new LambdaQueryWrapper<AiChatMessage>()
                .eq(AiChatMessage::getSessionId, session.getId())
                .orderByAsc(AiChatMessage::getId)
                .last("LIMIT 200"));
        List<Map<String, Object>> out = new ArrayList<>();
        for (AiChatMessage m : rows) {
            out.add(Map.of("role", m.getRole(), "content", m.getContent(), "createdAt", m.getCreatedAt()));
        }
        return out;
    }

    public Map<String, Object> deleteSession(Long userId, Long sessionId) {
        AiChatSession session = ownedSession(userId, sessionId);
        messageMapper.delete(new LambdaQueryWrapper<AiChatMessage>().eq(AiChatMessage::getSessionId, session.getId()));
        sessionMapper.deleteById(session.getId());
        return Map.of("id", sessionId, "deleted", true);
    }

    // ------------------------------------------------------------------

    private AiChatSession resolveSession(Long userId, Long sessionId, String firstMessage) {
        if (sessionId != null) return ownedSession(userId, sessionId);
        AiChatSession s = new AiChatSession();
        s.setUserId(userId);
        s.setTitle(firstMessage.length() > 24 ? firstMessage.substring(0, 24) + "…" : firstMessage);
        sessionMapper.insert(s);
        return s;
    }

    private AiChatSession ownedSession(Long userId, Long sessionId) {
        AiChatSession s = sessionMapper.selectById(sessionId);
        if (s == null || !s.getUserId().equals(userId)) throw new BusinessException(404, "对话不存在");
        return s;
    }

    private boolean mentionsContext(String text) {
        for (String k : CONTEXT_KEYWORDS) {
            if (text.contains(k)) return true;
        }
        return false;
    }

    /** 持仓快照摘要：无持仓或组装失败返回 null（不注入、不报错）。 */
    private String portfolioContext(Long userId) {
        try {
            Map<String, Object> advice = portfolioService.advice(userId, BigDecimal.ZERO);
            if (advice == null || advice.isEmpty()) return null;
            StringBuilder sb = new StringBuilder();
            sb.append("总资产: ").append(advice.get("totalAssets"));
            sb.append("; 现金: ").append(advice.get("cash"));
            sb.append("; 持仓市值: ").append(advice.get("totalMarketValue"));
            Object positions = advice.get("positions");
            if (positions != null) sb.append("; 持仓明细: ").append(positions);
            Object insights = advice.get("insights");
            if (insights != null) sb.append("; 规则建议: ").append(insights);
            return sb.toString();
        } catch (Exception e) {
            return null;
        }
    }
}
