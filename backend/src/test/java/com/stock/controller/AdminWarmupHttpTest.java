package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.controller.admin.AdminTaskController;
import com.stock.exception.BusinessException;
import com.stock.exception.GlobalExceptionHandler;
import com.stock.service.DataService;
import com.stock.service.admin.AdminAuditService;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class AdminWarmupHttpTest {

    @ParameterizedTest
    @ValueSource(strings = {"/api/admin/warmup", "/api/admin/tasks/run"})
    void unavailableAdmissionKeepsHttp503AndActionableMessage(String path) throws Exception {
        DataService service = mock(DataService.class);
        AdminAuditService audit = mock(AdminAuditService.class);
        JSONObject unavailable = new JSONObject();
        unavailable.put("upstream_status", 503);
        unavailable.put("error", "任务线程启动失败，请稍后重试");
        when(service.adminWarmupStart("postmarket")).thenReturn(unavailable);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new AdminController(service), new AdminTaskController(service, audit))
                .setControllerAdvice(new GlobalExceptionHandler()).build();
        mvc.perform(post(path).param("job", "postmarket").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"job\":\"postmarket\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value(503))
                .andExpect(jsonPath("$.message").value("任务线程启动失败，请稍后重试"));
        verifyNoInteractions(audit);
    }

    @ParameterizedTest
    @ValueSource(ints = {500, 502, 504})
    void otherBusinessServerCodesAreNotGrantedA5xxTransportStatus(int code) throws Exception {
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new TestErrors())
                .setControllerAdvice(new GlobalExceptionHandler()).build();
        mvc.perform(get("/_test/business/{code}", code)).andExpect(status().isBadRequest());
    }

    @RestController
    static class TestErrors {
        @GetMapping("/_test/business/{code}")
        public void error(@PathVariable int code) {
            throw new BusinessException(code, "caller-safe error");
        }
    }
}
