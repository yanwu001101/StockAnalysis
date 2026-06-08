package com.stock.service;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.exception.BusinessException;
import com.stock.mapper.PortfolioPositionMapper;
import com.stock.model.entity.PortfolioPosition;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;

@Service
public class PortfolioService {

    private final PortfolioPositionMapper positionMapper;
    private final DataService dataService;

    public PortfolioService(PortfolioPositionMapper positionMapper, DataService dataService) {
        this.positionMapper = positionMapper;
        this.dataService = dataService;
    }

    public List<Map<String, Object>> list(Long userId) {
        List<PortfolioPosition> rows = positionMapper.selectList(new LambdaQueryWrapper<PortfolioPosition>()
            .eq(PortfolioPosition::getUserId, userId)
            .orderByDesc(PortfolioPosition::getUpdatedAt));
        List<Map<String, Object>> out = new ArrayList<>();
        for (PortfolioPosition row : rows) {
            out.add(view(row, null, null));
        }
        return out;
    }

    public Map<String, Object> upsert(Long userId, Map<String, Object> body) {
        String code = normCode(body.get("code"));
        if (code.isEmpty()) throw new BusinessException("缺少股票代码");
        BigDecimal shares = decimal(body.get("shares"), BigDecimal.ZERO);
        BigDecimal avgCost = decimal(body.get("avgCost"), BigDecimal.ZERO);
        if (shares.compareTo(BigDecimal.ZERO) <= 0) throw new BusinessException("持仓数量必须大于 0");
        if (avgCost.compareTo(BigDecimal.ZERO) <= 0) throw new BusinessException("成本价必须大于 0");

        PortfolioPosition row = null;
        Object idObj = body.get("id");
        if (idObj != null && !idObj.toString().isBlank()) {
            row = positionMapper.selectOne(new LambdaQueryWrapper<PortfolioPosition>()
                .eq(PortfolioPosition::getId, Long.valueOf(idObj.toString()))
                .eq(PortfolioPosition::getUserId, userId));
            if (row == null) throw new BusinessException(404, "持仓不存在");
        }
        if (row == null) {
            row = positionMapper.selectOne(new LambdaQueryWrapper<PortfolioPosition>()
                .eq(PortfolioPosition::getUserId, userId)
                .eq(PortfolioPosition::getCode, code));
        }
        if (row == null) {
            row = new PortfolioPosition();
            row.setUserId(userId);
            row.setCode(code);
        }

        row.setName(string(body.get("name")));
        if (row.getName().isEmpty()) {
            try {
                JSONObject detail = dataService.getStockDetail(code);
                row.setName(detail == null ? "" : string(detail.getString("name")));
            } catch (Exception ignored) {
                row.setName("");
            }
        }
        row.setShares(shares);
        row.setAvailableShares(decimal(body.get("availableShares"), shares));
        row.setAvgCost(avgCost);
        row.setTargetWeight(decimal(body.get("targetWeight"), new BigDecimal("20")));
        row.setSource(stringOr(body.get("source"), "manual"));
        row.setNotes(string(body.get("notes")));

        if (row.getId() == null) positionMapper.insert(row);
        else positionMapper.updateById(row);
        return view(row, null, null);
    }

    public Map<String, Object> importText(Long userId, Map<String, Object> body) {
        String text = string(body.get("text"));
        if (text.isEmpty()) throw new BusinessException("请先粘贴持仓表内容");
        BigDecimal defaultTargetWeight = decimal(body.get("targetWeight"), new BigDecimal("20"));
        String[] rawLines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n");
        List<String> lines = new ArrayList<>();
        for (String raw : rawLines) {
            if (!raw.trim().isEmpty()) lines.add(raw.trim());
        }
        if (lines.isEmpty()) throw new BusinessException("没有识别到持仓数据");

        List<String> first = splitRow(lines.get(0));
        boolean hasHeader = looksLikeHeader(first);
        HeaderIndex idx = hasHeader ? headerIndex(first) : HeaderIndex.fallback();
        int imported = 0;
        int skipped = 0;
        List<String> errors = new ArrayList<>();

        for (int i = hasHeader ? 1 : 0; i < lines.size(); i++) {
            List<String> row = splitRow(lines.get(i));
            if (row.size() < 3) {
                skipped++;
                errors.add("第 " + (i + 1) + " 行列数不足");
                continue;
            }
            String code = normCode(getCell(row, idx.code));
            BigDecimal shares = decimal(getCell(row, idx.shares), BigDecimal.ZERO);
            BigDecimal avgCost = decimal(getCell(row, idx.avgCost), BigDecimal.ZERO);
            if (code.isEmpty() || shares.compareTo(BigDecimal.ZERO) <= 0 || avgCost.compareTo(BigDecimal.ZERO) <= 0) {
                skipped++;
                errors.add("第 " + (i + 1) + " 行缺少代码、持仓数量或成本价");
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("code", code);
            item.put("name", getCell(row, idx.name));
            item.put("shares", shares);
            item.put("availableShares", idx.availableShares >= 0 ? decimal(getCell(row, idx.availableShares), shares) : shares);
            item.put("avgCost", avgCost);
            item.put("targetWeight", defaultTargetWeight);
            item.put("source", stringOr(body.get("source"), "import_text"));
            item.put("notes", "导入持仓");
            upsert(userId, item);
            imported++;
        }
        if (imported == 0) throw new BusinessException("未导入任何持仓，请检查表头是否包含股票代码、持仓数量、成本价");

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("imported", imported);
        out.put("skipped", skipped);
        out.put("errors", errors);
        out.put("positions", list(userId));
        return out;
    }

    public void delete(Long userId, Long id) {
        int n = positionMapper.delete(new LambdaQueryWrapper<PortfolioPosition>()
            .eq(PortfolioPosition::getId, id)
            .eq(PortfolioPosition::getUserId, userId));
        if (n == 0) throw new BusinessException(404, "持仓不存在");
    }

    public Map<String, Object> advice(Long userId, BigDecimal cash) {
        return advice(userId, cash, "balanced");
    }

    public Map<String, Object> advice(Long userId, BigDecimal cash, String mode) {
        return advice(userId, cash, mode, null);
    }

    public Map<String, Object> advice(Long userId, BigDecimal cash, String mode, Object strategyConfigObj) {
        AdviceProfile profile = AdviceProfile.of(mode);
        JSONObject strategyConfig = strategyConfig(strategyConfigObj);
        List<PortfolioPosition> rows = positionMapper.selectList(new LambdaQueryWrapper<PortfolioPosition>()
            .eq(PortfolioPosition::getUserId, userId)
            .orderByDesc(PortfolioPosition::getUpdatedAt));
        List<AdviceInput> inputs = new ArrayList<>();
        BigDecimal totalMarketValue = BigDecimal.ZERO;
        for (PortfolioPosition row : rows) {
            JSONObject detail = safeDetail(row.getCode());
            JSONObject strategies = safeStrategies(row.getCode(), strategyConfig);
            BigDecimal price = decimal(detail == null ? null : detail.get("price"), BigDecimal.ZERO);
            BigDecimal value = price.multiply(nz(row.getShares()));
            totalMarketValue = totalMarketValue.add(value);
            inputs.add(new AdviceInput(row, detail, strategies, price, value));
        }
        BigDecimal totalAssets = totalMarketValue.add(nz(cash));
        List<Map<String, Object>> items = new ArrayList<>();
        for (AdviceInput in : inputs) {
            items.add(adviceView(in, totalAssets, profile));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("totalMarketValue", money(totalMarketValue));
        result.put("cash", money(nz(cash)));
        result.put("totalAssets", money(totalAssets));
        result.put("positions", items);
        result.put("insights", portfolioInsights(items, totalAssets, profile));
        result.put("mode", profile.mode);
        result.put("modeLabel", profile.label);
        result.put("strategyConfigApplied", strategyConfig != null && !strategyConfig.isEmpty());
        result.put("sync", thsSyncStatus());
        return result;
    }

    public Map<String, Object> thsSyncStatus() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("provider", "ths");
        out.put("status", "manual_import");
        out.put("canAutoSync", false);
        out.put("message", "暂未接入同花顺账号直连；可以先把同花顺或券商导出的持仓表复制粘贴导入。");
        out.put("nextSteps", List.of("在同花顺或券商客户端导出/复制持仓表", "粘贴包含股票代码、持仓数量、成本价的表格内容", "不要在本系统输入交易密码"));
        return out;
    }

    private Map<String, Object> adviceView(AdviceInput in, BigDecimal totalAssets, AdviceProfile profile) {
        PortfolioPosition row = in.row;
        BigDecimal shares = nz(row.getShares());
        BigDecimal avgCost = nz(row.getAvgCost());
        BigDecimal costValue = avgCost.multiply(shares);
        BigDecimal pnl = in.marketValue.subtract(costValue);
        BigDecimal pnlPct = costValue.compareTo(BigDecimal.ZERO) > 0
            ? pnl.multiply(new BigDecimal("100")).divide(costValue, 4, RoundingMode.HALF_UP)
            : BigDecimal.ZERO;
        BigDecimal weight = totalAssets.compareTo(BigDecimal.ZERO) > 0
            ? in.marketValue.multiply(new BigDecimal("100")).divide(totalAssets, 4, RoundingMode.HALF_UP)
            : BigDecimal.ZERO;
        double score = dbl(in.strategies == null ? null : firstNonNull(in.strategies.get("total"), in.strategies.get("composite_score")));
        String signal = in.strategies == null ? "neutral" : stringOr(in.strategies.get("signal"), "neutral");
        double changePct = dbl(in.detail == null ? null : in.detail.get("changePercent"));
        BigDecimal sellAbove = avgCost.multiply(profile.sellAboveMult);
        BigDecimal buyBelow = avgCost.multiply(profile.buyBelowMult);
        boolean priceKnown = nz(in.price).compareTo(BigDecimal.ZERO) > 0;

        List<String> reasons = new ArrayList<>();
        List<String> steps = new ArrayList<>();
        String action = "hold";
        String label = "持有观察";
        String type = "info";
        int confidence = 50;
        BigDecimal suggestedShares = BigDecimal.ZERO;

        if (!priceKnown) {
            // 没有实时行情(冷缓存/停牌/数据源不可用)。不要用 0 市值伪造 -100% 浮亏,
            // 改为只按策略信号给出"关注/观望"级别提示,等价格恢复后再确认买卖点。
            pnl = BigDecimal.ZERO;
            pnlPct = BigDecimal.ZERO;
            if (score >= profile.addScore) {
                action = "watch"; label = "关注(待行情)"; type = "success"; confidence = 55;
                reasons.add("策略评分较高,但实时行情暂不可用;先列入关注,价格恢复后再确认买点。");
            } else if (score < profile.reduceScore) {
                action = "watch_weak"; label = "偏弱观望(待行情)"; type = "warning"; confidence = 55;
                reasons.add("策略评分偏弱,且实时行情暂不可用;暂不加仓,等行情恢复再决定是否减仓。");
            } else {
                label = "持有观察(待行情)";
                reasons.add("实时行情暂不可用,暂以策略信号为准,价格恢复后再判断买卖点。");
            }
            steps.add("等待行情刷新(盘中或数据源恢复后重试),再结合成本价与策略信号确认操作。");
        } else if (pnlPct.compareTo(profile.stopLossPct) <= 0 && score < profile.weakScore) {
            action = "stop_loss";
            label = "止损/减仓";
            type = "danger";
            confidence = 82;
            suggestedShares = shares.multiply(new BigDecimal("0.5"));
            reasons.add("浮亏超过 " + pct(profile.stopLossPct.abs()) + "%，且策略评分偏弱。");
            steps.add("先卖出约一半可用股数，避免亏损继续扩大。");
        } else if (score >= profile.addScore && pnlPct.compareTo(profile.addMaxProfitPct) < 0 && weight.compareTo(nz(row.getTargetWeight())) < 0) {
            action = "add";
            label = profile.aggressive ? "收益优先加仓" : "可小幅加仓";
            type = "success";
            confidence = profile.aggressive ? 78 : 72;
            suggestedShares = roundLot(in.marketValue.compareTo(BigDecimal.ZERO) > 0
                ? shares.multiply(profile.addShareRatio) : new BigDecimal("100"));
            reasons.add("策略评分较高，当前仓位未超过目标仓位。");
            steps.add(profile.aggressive
                ? "分两到三笔加仓，强势趋势未破时允许追随，不要单日满仓。"
                : "分批买入，不要一次打满；优先等回落到成本价附近或分时企稳。");
        } else if (profile.aggressive && score >= 62 && pnlPct.compareTo(new BigDecimal("5")) >= 0 && changePct < 4) {
            action = "hold";
            label = "强势持有";
            type = "success";
            confidence = 74;
            reasons.add("已有利润但策略仍偏强，收益优先模式下先让利润奔跑。");
            steps.add("先不急着落袋；只要未跌破低吸线/趋势线，优先持有，回撤再做 T。");
        } else if (pnlPct.compareTo(profile.takeProfitPct) >= 0 && (score < profile.takeProfitWeakScore || changePct > profile.hotChangePct)) {
            action = "take_profit";
            label = "高抛/落袋";
            type = "warning";
            confidence = 76;
            suggestedShares = shares.multiply(profile.takeProfitShareRatio);
            reasons.add("已有较明显浮盈，且短线继续追高的性价比下降。");
            steps.add(profile.aggressive ? "只卖一小部分锁利润，保留大部分仓位继续跟随趋势。" : "可卖出约三分之一，保留底仓继续观察。");
        } else if (changePct >= profile.tSellChangePct && pnlPct.compareTo(BigDecimal.ZERO) > 0 && score < profile.tSellMaxScore) {
            action = "t_sell";
            label = "做T-先高抛";
            type = "warning";
            confidence = 68;
            suggestedShares = shares.multiply(profile.tShareRatio);
            reasons.add("今日涨幅较大且持仓有利润，适合考虑先卖一部分做 T。");
            steps.add("只用可用股数的一小部分高抛，尾盘或回落后再考虑接回。");
        } else if (changePct <= profile.tBuyChangePct && score >= profile.tBuyScore) {
            action = "t_buy";
            label = "做T-低吸观察";
            type = "success";
            confidence = 66;
            suggestedShares = roundLot(shares.multiply(profile.tBuyShareRatio));
            reasons.add("今日回落较多，但策略评分没有明显转弱。");
            steps.add(profile.aggressive ? "允许低吸稍大一笔，但必须留现金，跌破支撑就停止加。" : "只低吸一小笔，若继续跌破成本线/支撑位，不要继续摊大。");
        } else if (score < profile.reduceScore) {
            action = "reduce";
            label = "减仓观察";
            type = "danger";
            confidence = 70;
            suggestedShares = shares.multiply(new BigDecimal("0.33"));
            reasons.add("策略评分偏弱，暂不适合扩大仓位。");
            steps.add("反弹时优先降低仓位，等评分修复后再考虑买回。");
        } else {
            reasons.add("当前没有强买卖信号，适合按计划持有。");
            steps.add("新手优先管住仓位：不追涨、不满仓、跌破止损线先减。");
        }

        if (weight.compareTo(new BigDecimal("35")) > 0) {
            reasons.add("单只股票仓位超过 35%，波动会明显影响账户。");
            if (!"danger".equals(type)) type = "warning";
        }
        if ("bearish".equals(signal)) reasons.add("综合策略信号偏空。");
        if ("bullish".equals(signal)) reasons.add("综合策略信号偏多。");

        suggestedShares = executableShares(action, suggestedShares, nz(row.getAvailableShares()));
        Map<String, Object> consensus = strategyConsensus(in.strategies);
        String noAiSummary = noAiSummary(label, score, pnlPct, weight, consensus, priceKnown);
        Map<String, Object> out = view(row, in.detail, in.strategies);
        out.put("marketValue", money(in.marketValue));
        out.put("costValue", money(costValue));
        out.put("pnl", money(pnl));
        out.put("pnlPercent", pct(pnlPct));
        out.put("weight", pct(weight));
        out.put("strategyScore", round(score, 2));
        out.put("strategySignal", signal);
        out.put("action", action);
        out.put("actionLabel", label);
        out.put("actionType", type);
        out.put("confidence", confidence);
        out.put("suggestedShares", suggestedShares.intValue());
        out.put("suggestedAmount", money(suggestedShares.multiply(in.price)));
        out.put("buyBelow", money(buyBelow));
        out.put("sellAbove", money(sellAbove));
        out.put("reasons", reasons);
        out.put("steps", steps);
        out.put("priority", priority(action, confidence, weight));
        out.put("strategyConsensus", consensus);
        out.put("ruleSummary", noAiSummary);
        out.put("adviceMode", profile.mode);
        out.put("priceAvailable", priceKnown);
        return out;
    }

    private Map<String, Object> view(PortfolioPosition row, JSONObject detail, JSONObject strategies) {
        JSONObject d = detail != null ? detail : safeDetail(row.getCode());
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", row.getId());
        out.put("code", row.getCode());
        out.put("name", !string(row.getName()).isEmpty() ? row.getName() : (d == null ? "" : d.getString("name")));
        out.put("shares", nz(row.getShares()));
        out.put("availableShares", nz(row.getAvailableShares()));
        out.put("avgCost", money(nz(row.getAvgCost())));
        out.put("targetWeight", pct(nz(row.getTargetWeight())));
        out.put("source", row.getSource());
        out.put("notes", row.getNotes());
        out.put("price", money(decimal(d == null ? null : d.get("price"), BigDecimal.ZERO)));
        out.put("changePercent", round(dbl(d == null ? null : d.get("changePercent")), 2));
        out.put("industry", d == null ? "" : d.getString("industry"));
        out.put("updatedAt", row.getUpdatedAt());
        if (strategies != null) {
            out.put("strategyScore", round(dbl(firstNonNull(strategies.get("total"), strategies.get("composite_score"))), 2));
            out.put("strategySignal", strategies.getString("signal"));
        }
        return out;
    }

    private Map<String, Object> portfolioInsights(List<Map<String, Object>> items, BigDecimal totalAssets, AdviceProfile profile) {
        int add = 0, hold = 0, reduce = 0, t = 0, risk = 0;
        double weightedScore = 0, weightSum = 0;
        double simpleSum = 0; int scored = 0;
        for (Map<String, Object> item : items) {
            String action = string(item.get("action"));
            double weight = dbl(item.get("weight"));
            double score = dbl(item.get("strategyScore"));
            if ("add".equals(action) || "t_buy".equals(action)) add++;
            else if ("reduce".equals(action) || "stop_loss".equals(action)) reduce++;
            else if ("t_sell".equals(action) || "take_profit".equals(action)) t++;
            else hold++;
            if ("danger".equals(item.get("actionType"))) risk++;
            if (weight > 0) {
                weightedScore += score * weight;
                weightSum += weight;
            }
            if (score > 0) { simpleSum += score; scored++; }
        }
        // 有行情时按市值加权;行情普遍缺失(weightSum=0)时退回等权平均,
        // 避免头部"策略均分"在拿不到价格时恒为 0。
        double avgScore = weightSum > 0 ? weightedScore / weightSum
            : (scored > 0 ? simpleSum / scored : 0);
        String riskLevel = risk > 0 || reduce > 0 ? "需要控风险" : (add > 0 ? "可进攻观察" : "稳态观察");
        List<String> bullets = new ArrayList<>();
        bullets.add("当前组合按规则引擎可直接分析，不依赖 AI 配置；当前模式：" + profile.label + "。");
        if (profile.aggressive) bullets.add("收益优先会放宽过早止盈、提高加仓比例，但回撤也会更大。");
        if (reduce > 0 || risk > 0) bullets.add("优先处理减仓/止损标的，再考虑做 T 或加仓。");
        if (add > 0) bullets.add("有可加仓/低吸标的时仍建议分批，单笔不要打满。");
        if (items.isEmpty()) bullets.add("先录入或导入持仓，系统会生成操作清单。");
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("avgStrategyScore", round(avgScore, 2));
        out.put("riskLevel", riskLevel);
        out.put("addCount", add);
        out.put("holdCount", hold);
        out.put("reduceCount", reduce);
        out.put("tCount", t);
        out.put("totalAssets", money(totalAssets));
        out.put("bullets", bullets);
        return out;
    }

    private Map<String, Object> strategyConsensus(JSONObject strategies) {
        Map<String, Object> out = new LinkedHashMap<>();
        List<Map<String, Object>> bullish = new ArrayList<>();
        List<Map<String, Object>> bearish = new ArrayList<>();
        List<Map<String, Object>> triggered = new ArrayList<>();
        int effective = 0, total = 0;
        if (strategies != null) {
            JSONObject agg = strategies.getJSONObject("aggregate");
            if (agg != null) {
                out.put("effective", agg.getIntValue("effective"));
                out.put("bullish", agg.getIntValue("bullish"));
                out.put("bearish", agg.getIntValue("bearish"));
                out.put("triggered", agg.getIntValue("triggered"));
            }
            JSONArray list = strategies.getJSONArray("strategies_list");
            if (list != null) {
                total = list.size();
                for (Object obj : list) {
                    JSONObject s = JSONObject.from(obj);
                    if (s.getBooleanValue("no_data")) continue;
                    JSONObject details = s.getJSONObject("details");
                    if (details != null && details.getBooleanValue("disabled")) continue;
                    effective++;
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", s.getString("id"));
                    row.put("name", s.getString("name"));
                    row.put("score", round(s.getDoubleValue("score"), 2));
                    row.put("signal", s.getString("signal"));
                    row.put("triggered", s.getBooleanValue("triggered"));
                    row.put("detail", strategyDetailText(s.getString("id"), details));
                    if ("bullish".equals(s.getString("signal"))) bullish.add(row);
                    if ("bearish".equals(s.getString("signal"))) bearish.add(row);
                    if (s.getBooleanValue("triggered")) triggered.add(row);
                }
            }
        }
        Comparator<Map<String, Object>> byScore = Comparator.comparingDouble(x -> -dbl(x.get("score")));
        bullish.sort(byScore);
        bearish.sort(Comparator.comparingDouble(x -> dbl(x.get("score"))));
        triggered.sort(byScore);
        out.putIfAbsent("effective", effective);
        out.putIfAbsent("bullish", bullish.size());
        out.putIfAbsent("bearish", bearish.size());
        out.putIfAbsent("triggered", triggered.size());
        out.put("total", total);
        out.put("topBullish", bullish.stream().limit(4).toList());
        out.put("topBearish", bearish.stream().limit(4).toList());
        out.put("triggeredStrategies", triggered.stream().limit(5).toList());
        return out;
    }

    private String strategyDetailText(String id, JSONObject details) {
        if (details == null) return "";
        if ("fund_price_divergence".equals(id)) {
            if (details.getBooleanValue("accumulation_on_pullback")) return "下跌中主力回流，偏吸筹观察";
            if (details.getBooleanValue("distribution_warning")) return "上涨中主力流出，警惕派发";
        }
        if ("ashare_short_reversal".equals(id)) {
            if (details.getBooleanValue("controlled_pullback")) return "短期超跌但基本面锚还在";
            if (details.getBooleanValue("overheated_warning")) return "短线涨幅过热，追高性价比下降";
        }
        if ("conservative_formula".equals(id)) {
            if (details.getBooleanValue("low_vol") && details.getBooleanValue("trend_ok")) return "低波动且趋势向上";
        }
        if ("rsrs_timing".equals(id)) {
            if (details.getBooleanValue("breakout_quality")) return "支撑阻力强度转强，突破质量较好";
            if (details.getBooleanValue("support_weakening")) return "支撑强度转弱，谨慎追买";
        }
        if ("trend_pullback_stop".equals(id)) {
            if (details.getBooleanValue("healthy_pullback")) return "趋势未破的健康回撤";
            if (details.getBooleanValue("trailing_stop_break")) return "跌破移动止盈/风控线";
            if (details.getBooleanValue("ma60_break")) return "跌破中期趋势线";
        }
        if ("daily_momentum_reversal_t".equals(id)) {
            if (details.getBooleanValue("fresh_daily_momentum")) return "日频动量刚启动，适合短线跟随";
            if (details.getBooleanValue("trend_dip_for_t")) return "趋势内回落，适合做 T 低吸观察";
            if (details.getBooleanValue("overheat_reversal_risk")) return "短线过热，警惕冲高回落";
        }
        if ("growth_trend_accelerator".equals(id)) {
            if (details.getBooleanValue("profit_accelerating") && details.getBooleanValue("trend_confirmed")) return "业绩加速且趋势确认";
            if (details.getBooleanValue("too_extended")) return "成长趋势仍在但短线涨幅过大";
        }
        if ("multi_horizon_momentum".equals(id) && details.containsKey("aligned")) {
            return "多周期方向一致：" + details.getString("aligned");
        }
        if ("low_volatility".equals(id) && details.getBooleanValue("trend_ok")) return "波动较低且趋势未破";
        if ("fifty_two_week_high".equals(id) && details.getBooleanValue("very_close")) return "接近 52 周高点";
        if ("accruals_quality".equals(id) && details.getBooleanValue("cash_driven")) return "利润现金含量较好";
        return "";
    }

    private String noAiSummary(String label, double score, BigDecimal pnlPct,
                               BigDecimal weight, Map<String, Object> consensus, boolean priceKnown) {
        int bullish = (int) dbl(consensus.get("bullish"));
        int bearish = (int) dbl(consensus.get("bearish"));
        int triggered = (int) dbl(consensus.get("triggered"));
        String pnlText = priceKnown ? (pct(pnlPct) + "%,组合仓位 " + pct(weight) + "%") : "待行情";
        return "规则结论：" + label + "；策略分 " + round(score, 1)
            + "，看多/看空 " + bullish + "/" + bearish
            + "，触发 " + triggered + " 个策略；浮盈亏 " + pnlText + "。";
    }

    private int priority(String action, int confidence, BigDecimal weight) {
        int p = confidence;
        if ("stop_loss".equals(action) || "reduce".equals(action)) p += 15;
        if ("t_sell".equals(action) || "take_profit".equals(action)) p += 8;
        if (weight.compareTo(new BigDecimal("35")) > 0) p += 10;
        return Math.min(100, p);
    }

    private JSONObject safeDetail(String code) {
        try { return dataService.getStockDetail(code); } catch (Exception ignored) { return null; }
    }

    private JSONObject safeStrategies(String code) {
        return safeStrategies(code, null);
    }

    private JSONObject safeStrategies(String code, JSONObject strategyConfig) {
        try { return dataService.getStockStrategies(code, strategyConfig); } catch (Exception ignored) { return null; }
    }

    private static JSONObject strategyConfig(Object value) {
        if (value == null) return null;
        if (value instanceof JSONObject obj) return obj;
        if (value instanceof Map<?, ?> map) {
            JSONObject obj = new JSONObject();
            for (Map.Entry<?, ?> e : map.entrySet()) {
                if (e.getKey() != null) obj.put(String.valueOf(e.getKey()), e.getValue());
            }
            return obj;
        }
        try {
            return JSONObject.parseObject(value.toString());
        } catch (Exception ignored) {
            return null;
        }
    }

    private static String normCode(Object value) {
        String text = string(value).replaceAll("\\D", "");
        if (text.length() > 6) text = text.substring(text.length() - 6);
        return text.isEmpty() ? "" : String.format("%6s", text).replace(' ', '0');
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
        try {
            if (value instanceof BigDecimal bd) return bd;
            String text = value.toString().replace(",", "").replace("%", "").trim();
            if (text.isEmpty() || "--".equals(text)) return fallback;
            return new BigDecimal(text);
        } catch (Exception e) {
            return fallback;
        }
    }

    private static List<String> splitRow(String line) {
        if (line.contains("\t")) return splitDelimited(line, '\t');
        if (line.contains(",")) return splitDelimited(line, ',');
        return Arrays.asList(line.trim().split("\\s+"));
    }

    private static List<String> splitDelimited(String line, char delimiter) {
        List<String> cells = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char ch = line.charAt(i);
            if (ch == '"') {
                quoted = !quoted;
            } else if (ch == delimiter && !quoted) {
                cells.add(cleanCell(current.toString()));
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        cells.add(cleanCell(current.toString()));
        return cells;
    }

    private static String cleanCell(String value) {
        String s = value == null ? "" : value.trim();
        if (s.length() >= 2 && s.startsWith("\"") && s.endsWith("\"")) {
            s = s.substring(1, s.length() - 1);
        }
        return s.trim();
    }

    private static boolean looksLikeHeader(List<String> cells) {
        String joined = String.join("", cells);
        return joined.contains("代码") || joined.contains("证券") || joined.contains("股票")
            || joined.contains("持仓") || joined.contains("成本") || joined.toLowerCase(Locale.ROOT).contains("code");
    }

    private static HeaderIndex headerIndex(List<String> headers) {
        return new HeaderIndex(
            findColumn(headers, "股票代码", "证券代码", "代码", "code"),
            findColumn(headers, "股票名称", "证券名称", "名称", "name"),
            findColumn(headers, "持仓数量", "持仓股数", "股票余额", "股份余额", "当前持仓", "数量", "shares"),
            findColumn(headers, "可用数量", "可用股数", "可卖数量", "可卖股数", "可用余额", "available"),
            findColumn(headers, "成本价", "成本价格", "持仓成本", "买入均价", "成本", "avgcost")
        );
    }

    private static int findColumn(List<String> headers, String... names) {
        for (int i = 0; i < headers.size(); i++) {
            String h = headers.get(i).replace(" ", "").replace("_", "").toLowerCase(Locale.ROOT);
            for (String name : names) {
                String key = name.replace(" ", "").replace("_", "").toLowerCase(Locale.ROOT);
                if (h.equals(key) || h.contains(key)) return i;
            }
        }
        return -1;
    }

    private static String getCell(List<String> row, int index) {
        return index >= 0 && index < row.size() ? row.get(index) : "";
    }

    private static BigDecimal nz(BigDecimal v) {
        return v == null ? BigDecimal.ZERO : v;
    }

    private static double dbl(Object value) {
        if (value == null) return 0.0;
        try { return Double.parseDouble(value.toString()); } catch (Exception e) { return 0.0; }
    }

    private static Object firstNonNull(Object a, Object b) {
        return a != null ? a : b;
    }

    private static BigDecimal roundLot(BigDecimal shares) {
        if (shares == null || shares.compareTo(new BigDecimal("100")) < 0) return BigDecimal.ZERO;
        return shares.divide(new BigDecimal("100"), 0, RoundingMode.DOWN).multiply(new BigDecimal("100"));
    }

    private static BigDecimal executableShares(String action, BigDecimal raw, BigDecimal available) {
        BigDecimal v = raw == null ? BigDecimal.ZERO : raw.max(BigDecimal.ZERO);
        if (v.compareTo(BigDecimal.ZERO) <= 0) return BigDecimal.ZERO;
        if ("add".equals(action) || "t_buy".equals(action)) {
            return roundLot(v);
        }
        BigDecimal cap = available == null ? BigDecimal.ZERO : available.max(BigDecimal.ZERO);
        if (cap.compareTo(BigDecimal.ZERO) <= 0) return BigDecimal.ZERO;
        v = v.min(cap);
        if (v.compareTo(new BigDecimal("100")) < 0 && cap.compareTo(new BigDecimal("100")) >= 0) {
            return new BigDecimal("100");
        }
        if (v.compareTo(new BigDecimal("100")) >= 0) {
            return roundLot(v).min(cap);
        }
        return v;
    }

    private static double money(BigDecimal v) {
        return nz(v).setScale(2, RoundingMode.HALF_UP).doubleValue();
    }

    private static double pct(BigDecimal v) {
        return nz(v).setScale(2, RoundingMode.HALF_UP).doubleValue();
    }

    private static double round(double v, int scale) {
        return BigDecimal.valueOf(v).setScale(scale, RoundingMode.HALF_UP).doubleValue();
    }

    private record AdviceInput(
        PortfolioPosition row,
        JSONObject detail,
        JSONObject strategies,
        BigDecimal price,
        BigDecimal marketValue
    ) {}

    private record HeaderIndex(int code, int name, int shares, int availableShares, int avgCost) {
        private static HeaderIndex fallback() {
            return new HeaderIndex(0, 1, 2, 3, 4);
        }
    }

    private static class AdviceProfile {
        final String mode;
        final String label;
        final boolean aggressive;
        final BigDecimal stopLossPct;
        final double weakScore;
        final double addScore;
        final BigDecimal addMaxProfitPct;
        final BigDecimal addShareRatio;
        final BigDecimal takeProfitPct;
        final double takeProfitWeakScore;
        final double hotChangePct;
        final BigDecimal takeProfitShareRatio;
        final double tSellChangePct;
        final double tSellMaxScore;
        final BigDecimal tShareRatio;
        final double tBuyChangePct;
        final double tBuyScore;
        final BigDecimal tBuyShareRatio;
        final double reduceScore;
        final BigDecimal buyBelowMult;
        final BigDecimal sellAboveMult;

        private AdviceProfile(String mode, String label, boolean aggressive,
                              String stopLossPct, double weakScore, double addScore,
                              String addMaxProfitPct, String addShareRatio,
                              String takeProfitPct, double takeProfitWeakScore,
                              double hotChangePct, String takeProfitShareRatio,
                              double tSellChangePct, double tSellMaxScore, String tShareRatio,
                              double tBuyChangePct, double tBuyScore, String tBuyShareRatio,
                              double reduceScore, String buyBelowMult, String sellAboveMult) {
            this.mode = mode;
            this.label = label;
            this.aggressive = aggressive;
            this.stopLossPct = new BigDecimal(stopLossPct);
            this.weakScore = weakScore;
            this.addScore = addScore;
            this.addMaxProfitPct = new BigDecimal(addMaxProfitPct);
            this.addShareRatio = new BigDecimal(addShareRatio);
            this.takeProfitPct = new BigDecimal(takeProfitPct);
            this.takeProfitWeakScore = takeProfitWeakScore;
            this.hotChangePct = hotChangePct;
            this.takeProfitShareRatio = new BigDecimal(takeProfitShareRatio);
            this.tSellChangePct = tSellChangePct;
            this.tSellMaxScore = tSellMaxScore;
            this.tShareRatio = new BigDecimal(tShareRatio);
            this.tBuyChangePct = tBuyChangePct;
            this.tBuyScore = tBuyScore;
            this.tBuyShareRatio = new BigDecimal(tBuyShareRatio);
            this.reduceScore = reduceScore;
            this.buyBelowMult = new BigDecimal(buyBelowMult);
            this.sellAboveMult = new BigDecimal(sellAboveMult);
        }

        static AdviceProfile of(String raw) {
            String mode = string(raw).toLowerCase(Locale.ROOT);
            if ("aggressive".equals(mode) || "growth".equals(mode)) {
                return new AdviceProfile("aggressive", "收益优先", true,
                    "-10", 42, 58, "10", "0.40",
                    "12", 48, 4.5, "0.20",
                    4.0, 65, "0.18",
                    -2.0, 50, "0.30",
                    34, "0.985", "1.055");
            }
            if ("conservative".equals(mode)) {
                return new AdviceProfile("conservative", "稳健防守", false,
                    "-7", 48, 68, "2", "0.18",
                    "5", 58, 2.8, "0.35",
                    2.2, 58, "0.25",
                    -3.0, 58, "0.15",
                    44, "0.970", "1.025");
            }
            return new AdviceProfile("balanced", "均衡", false,
                "-8", 45, 65, "3", "0.25",
                "6", 55, 3.0, "0.33",
                2.5, 100, "0.25",
                -2.5, 55, "0.20",
                40, "0.975", "1.025");
        }
    }
}
