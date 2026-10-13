package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.controller.admin.AdminTaskController;
import com.stock.exception.BusinessException;
import com.stock.service.DataService;
import com.stock.service.admin.AdminAuditService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockHttpServletRequest;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AdminWarmupContractTest {

    @ParameterizedTest
    @ValueSource(ints = {400, 409, 429, 503})
    void neitherSubmissionEntryPointWrapsRejectedAdmissionAsSuccess(int status) {
        DataService service = mock(DataService.class);
        AdminAuditService audit = mock(AdminAuditService.class);
        JSONObject result = new JSONObject();
        result.put("error", "任务暂不可提交，请稍后重试");
        result.put("upstream_status", status);
        when(service.adminWarmupStart("postmarket")).thenReturn(result);
        BusinessException oldFailure = assertThrows(BusinessException.class,
                () -> new AdminController(service).warmup("postmarket"));
        BusinessException newFailure = assertThrows(BusinessException.class,
                () -> new AdminTaskController(service, audit).run(Map.of("job", "postmarket"), new MockHttpServletRequest()));
        assertEquals(status, oldFailure.getCode());
        assertEquals(oldFailure.getMessage(), newFailure.getMessage());
        assertEquals(status, newFailure.getCode());
        verifyNoInteractions(audit); // A rejected job must not be logged as an accepted TASK_RUN.
    }

    @Test void successfulAdmissionWithNullErrorIsAcceptedAndAuditedOnce() {
        DataService service = mock(DataService.class);
        AdminAuditService audit = mock(AdminAuditService.class);
        JSONObject result = JSON.parseObject("{\"id\":\"run1\",\"status\":\"running\",\"error\":null}");
        when(service.adminWarmupStart("postmarket")).thenReturn(result);
        assertSame(result, new AdminController(service).warmup("postmarket").getData());
        var request = new MockHttpServletRequest();
        assertSame(result, new AdminTaskController(service, audit).run(Map.of(), request).getData());
        verify(audit).record(request, "TASK_RUN", "job:postmarket", result);
    }

    @ParameterizedTest
    @ValueSource(strings = {"failed", "partial"})
    void terminalJobBusinessErrorsRemainVisibleInStatusData(String status) {
        DataService service = mock(DataService.class);
        AdminAuditService audit = mock(AdminAuditService.class);
        JSONObject result = JSON.parseObject("{\"id\":\"run1\",\"error\":\"检查步骤明细\",\"steps\":[]}");
        result.put("status", status);
        when(service.getAdminWarmupStatus("run1")).thenReturn(result);
        assertSame(result, new AdminController(service).warmupStatus("run1").getData());
        assertSame(result, new AdminTaskController(service, audit).runs("run1").getData());
        verifyNoInteractions(audit);
    }

    @Test void transportFailureDuringStatusQueryIsNotWrappedAsSuccess() {
        DataService service = mock(DataService.class);
        JSONObject result = JSON.parseObject("{\"error\":\"任务记录不存在\",\"upstream_status\":404}");
        when(service.getAdminWarmupStatus("missing")).thenReturn(result);
        assertEquals(404, assertThrows(BusinessException.class,
                () -> new AdminController(service).warmupStatus("missing")).getCode());
        assertEquals(404, assertThrows(BusinessException.class,
                () -> new AdminTaskController(service, mock(AdminAuditService.class)).runs("missing")).getCode());
    }

    @Test void emptySubmissionResponseIsAVisibleFailureAtBothEntryPoints() {
        DataService service = mock(DataService.class);
        assertThrows(BusinessException.class, () -> new AdminController(service).warmup("postmarket"));
        assertThrows(BusinessException.class,
                () -> new AdminTaskController(service, mock(AdminAuditService.class))
                        .run(Map.of("job", "postmarket"), new MockHttpServletRequest()));
    }
}
