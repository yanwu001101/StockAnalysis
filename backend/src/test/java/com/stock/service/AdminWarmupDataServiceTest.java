package com.stock.service;

import com.alibaba.fastjson2.JSONObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;

import java.nio.charset.StandardCharsets;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AdminWarmupDataServiceTest {

    @SuppressWarnings("unchecked")
    private DataService service(RestTemplate rest) {
        DataService service = new DataService(rest, mock(RedisTemplate.class));
        ReflectionTestUtils.setField(service, "dataServiceUrl", "http://data-service:5001");
        return service;
    }

    static Stream<Arguments> admissionErrors() {
        return Stream.of(
                Arguments.of(HttpStatus.BAD_REQUEST, "任务参数无效", "WARMUP_INVALID"),
                Arguments.of(HttpStatus.CONFLICT, "同一任务正在运行，请等待完成", "WARMUP_ALREADY_RUNNING"),
                Arguments.of(HttpStatus.TOO_MANY_REQUESTS, "任务并发已满，请稍后重试", "WARMUP_CAPACITY"),
                Arguments.of(HttpStatus.SERVICE_UNAVAILABLE, "任务线程启动失败，请稍后重试", "WARMUP_UNAVAILABLE")
        );
    }

    @ParameterizedTest
    @MethodSource("admissionErrors")
    void admissionErrorsRetainTheirMessageCodeAndTransportStatus(HttpStatus status, String message, String code) {
        RestTemplate rest = mock(RestTemplate.class);
        JSONObject body = new JSONObject(); body.put("error", message); body.put("code", code);
        byte[] bytes = body.toJSONString().getBytes(StandardCharsets.UTF_8);
        HttpStatusCodeException error = status.is5xxServerError()
                ? HttpServerErrorException.create(status, "unavailable", HttpHeaders.EMPTY, bytes, StandardCharsets.UTF_8)
                : HttpClientErrorException.create(status, "rejected", HttpHeaders.EMPTY, bytes, StandardCharsets.UTF_8);
        when(rest.postForObject(anyString(), isNull(), eq(String.class))).thenThrow(error);
        JSONObject result = service(rest).adminWarmupStart("postmarket");
        assertEquals(message, result.getString("error"));
        assertEquals(code, result.getString("code"));
        assertEquals(status.value(), result.getIntValue("upstream_status"));
        verify(rest).postForObject("http://data-service:5001/api/admin/warmup?job=postmarket", null, String.class);
    }

    @Test void successfulStatusResponseCanContainAFailedJobWithoutBecomingARequestError() {
        RestTemplate rest = mock(RestTemplate.class);
        when(rest.getForObject(anyString(), eq(String.class))).thenReturn("""
                {"id":"run1","status":"failed","error":"所有数据源失败",
                 "outcome_version":1,"rows":0,"steps":[{"name":"daily_kline","status":"failed"}]}
                """);
        JSONObject result = service(rest).getAdminWarmupStatus("run1");
        assertEquals("failed", result.getString("status"));
        assertEquals("所有数据源失败", result.getString("error"));
        assertEquals(1, result.getJSONArray("steps").size());
        assertFalse(result.containsKey("upstream_status"));
    }

    @Test void missingRunIsMarkedAsAnHttpErrorNotAsAFailedCompletedRun() {
        RestTemplate rest = mock(RestTemplate.class);
        var error = HttpClientErrorException.create(HttpStatus.NOT_FOUND, "missing", HttpHeaders.EMPTY,
                "{\"error\":\"任务记录不存在\"}".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        when(rest.getForObject(anyString(), eq(String.class))).thenThrow(error);
        JSONObject result = service(rest).getAdminWarmupStatus("missing");
        assertEquals(404, result.getIntValue("upstream_status"));
        assertEquals("任务记录不存在", result.getString("error"));
    }

    @Test void malformedBodyAndUnrelatedAdminRoutesRetainTheGlobalErrorHandler() {
        RestTemplate rest = mock(RestTemplate.class);
        var error = HttpServerErrorException.create(HttpStatus.BAD_GATEWAY, "bad gateway", HttpHeaders.EMPTY,
                "<html>upstream error</html>".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        when(rest.postForObject(anyString(), isNull(), eq(String.class))).thenThrow(error);
        DataService service = service(rest);
        assertSame(error, assertThrows(HttpServerErrorException.class, () -> service.adminWarmupStart("postmarket")));
        assertSame(error, assertThrows(HttpServerErrorException.class, () -> service.adminCacheClear("ds:*")));
    }
}
