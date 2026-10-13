package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.service.DataService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ResearchJobOwnershipTest {
    @Test void callerHeadersAndBodyNeverOverrideTheAuthenticatedOwner() {
        DataService service = mock(DataService.class);
        when(service.submitResearchJob(anyString(), any(), anyLong())).thenReturn(new JSONObject());
        when(service.getResearchJob(anyString(), anyLong())).thenReturn(new JSONObject());
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setAttribute("userId", 7L);
        request.addHeader("X-Research-Owner", "99");
        request.addHeader("X-Research-Signature", "forged");
        JSONObject body = new JSONObject(); body.put("userId", 99); body.put("owner_id", 99);
        ResearchJobController controller = new ResearchJobController(service);
        controller.submit("backtest", body, request);
        controller.status("job", request);
        verify(service).submitResearchJob("/api/async/backtest", body, 7L);
        verify(service).getResearchJob("job", 7L);
    }

    @Test void bareOwnerHeaderDoesNotSubstituteForLogin() {
        DataService service = mock(DataService.class);
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Research-Owner", "7");
        request.addParameter("userId", "7");
        JSONObject body = new JSONObject(); body.put("owner_id", 7);
        ResearchJobController controller = new ResearchJobController(service);
        assertEquals(401, assertThrows(BusinessException.class,
                () -> controller.submit("backtest", body, request)).getCode());
        assertEquals(401, assertThrows(BusinessException.class,
                () -> controller.status("job", request)).getCode());
        verifyNoInteractions(service);
    }

    @ParameterizedTest @ValueSource(longs = {0, -1})
    void nonPositiveAuthenticatedClaimIsRejected(long owner) {
        DataService service = mock(DataService.class);
        MockHttpServletRequest request = new MockHttpServletRequest(); request.setAttribute("userId", owner);
        assertEquals(401, assertThrows(BusinessException.class,
                () -> new ResearchJobController(service).status("job", request)).getCode());
        verifyNoInteractions(service);
    }

    @ParameterizedTest @ValueSource(ints = {401, 404, 429, 503})
    void trustedUpstreamStatusIsNotCollapsedTo400(int status) {
        DataService service = mock(DataService.class);
        JSONObject error = new JSONObject(); error.put("error", "任务不可用"); error.put("upstream_status", status);
        when(service.getResearchJob("job", 7L)).thenReturn(error);
        MockHttpServletRequest request = new MockHttpServletRequest(); request.setAttribute("userId", 7L);
        assertEquals(status, assertThrows(BusinessException.class,
                () -> new ResearchJobController(service).status("job", request)).getCode());
    }
}
