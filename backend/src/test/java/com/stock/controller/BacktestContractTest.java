package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.BacktestRequest;
import com.stock.service.DataService;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class BacktestContractTest {
    private static MockHttpServletRequest request() {
        var request = new MockHttpServletRequest(); request.setAttribute("userId", 7L); return request;
    }

    @Test void allEntryPointsUseTheSameNullableResultContract() {
        DataService service = mock(DataService.class);
        JSONObject result = JSON.parseObject("""
                {"mode":"single","code":"600519","strategy_id":"quality_factor",
                 "expression":"rank(close)","engine_version":"test-v3",
                 "metrics":{"total_return":0,"max_drawdown":null},"signal_log":[],
                 "equity_curve":[],"trades":[],"picks":[]}
                """);
        when(service.runBacktest(any())).thenReturn(result);
        when(service.runAlphaBacktest(any())).thenReturn(result);
        JSONObject expected = (JSONObject) new BacktestController(service).backtest(new BacktestRequest()).getData();
        assertEquals(expected, new AlphaLabController(service).backtest(new JSONObject()).getData());
        for (String kind : new String[]{"backtest", "alphalab-backtest"}) {
            JSONObject job = new JSONObject();
            job.put("status", "DONE"); job.put("kind", kind); job.put("result", result); job.put("error", null);
            when(service.getResearchJob("job", 7L)).thenReturn(job);
            JSONObject response = (JSONObject) new ResearchJobController(service).status("job", request()).getData();
            assertEquals(expected, response.getJSONObject("result"));
            assertSame(result, job.get("result"), "Gateway must not mutate the upstream job object");
        }
        assertNull(expected.get("maxDrawdown"));
        assertNull(expected.get("winRate"));
        assertEquals(0, expected.get("totalReturn"));
    }

    @Test void doneJobWithBusinessErrorFailsInsteadOfRenderingEmptySuccess() {
        DataService service = mock(DataService.class);
        JSONObject result = JSON.parseObject("{\"error\":\"no price matrix\",\"error_kind\":\"coverage\"}");
        when(service.runBacktest(any())).thenReturn(result);
        when(service.runAlphaBacktest(any())).thenReturn(result);
        String expected = assertThrows(BusinessException.class,
                () -> new BacktestController(service).backtest(new BacktestRequest())).getMessage();
        assertEquals(expected, assertThrows(BusinessException.class,
                () -> new AlphaLabController(service).backtest(new JSONObject())).getMessage());
        for (String kind : new String[]{"backtest", "alphalab-backtest"}) {
            JSONObject job = new JSONObject();
            job.put("status", "DONE"); job.put("kind", kind); job.put("result", result);
            when(service.getResearchJob("job", 7L)).thenReturn(job);
            assertEquals(expected, assertThrows(BusinessException.class,
                    () -> new ResearchJobController(service).status("job", request())).getMessage());
        }
    }

    @Test void queuedJobNullErrorIsNotMistakenForFailure() {
        DataService service = mock(DataService.class);
        JSONObject queued = new JSONObject();
        queued.put("status", "QUEUED"); queued.put("error", null);
        when(service.submitResearchJob(any(), any(), anyLong())).thenReturn(queued);
        when(service.getResearchJob("job", 7L)).thenReturn(queued);
        ResearchJobController controller = new ResearchJobController(service);
        assertEquals(queued, controller.submit("backtest", new JSONObject(), request()).getData());
        assertEquals(queued, controller.status("job", request()).getData());
    }

    @Test void factorlabResultRemainsInItsOriginalResearchShape() {
        DataService service = mock(DataService.class);
        JSONObject job = JSON.parseObject("""
                {"status":"DONE","kind":"factorlab","error":null,
                 "result":{"error":"coverage insufficient","sample_info":{"periods":0}}}
                """);
        when(service.getResearchJob("job", 7L)).thenReturn(job);
        assertSame(job, new ResearchJobController(service).status("job", request()).getData());
    }

    @Test void completedBacktestWithoutResultIsNotAValidEmptyResult() {
        DataService service = mock(DataService.class);
        when(service.getResearchJob("job", 7L)).thenReturn(JSON.parseObject(
                "{\"status\":\"DONE\",\"kind\":\"backtest\",\"result\":null}"));
        assertEquals("回测无数据", assertThrows(BusinessException.class,
                () -> new ResearchJobController(service).status("job", request())).getMessage());
    }
}
