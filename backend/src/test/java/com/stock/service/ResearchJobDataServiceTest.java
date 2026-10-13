package com.stock.service;

import com.alibaba.fastjson2.JSONObject;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestTemplate;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ResearchJobDataServiceTest {

    @SuppressWarnings("unchecked")
    private DataService service(RestTemplate rest) {
        DataService service = new DataService(rest, mock(RedisTemplate.class));
        ReflectionTestUtils.setField(service, "dataServiceUrl", "http://data-service:5001");
        ReflectionTestUtils.setField(service, "researchSigningSecret", "test-only-research-secret-0123456789abcdef");
        return service;
    }

    @Test void fullQueueReturnsActionableStructuredError() {
        RestTemplate rest = mock(RestTemplate.class);
        var error = HttpClientErrorException.create(HttpStatus.TOO_MANY_REQUESTS, "queue full", HttpHeaders.EMPTY,
                "{\"error\":\"研究任务队列已满，请稍后重试\",\"code\":\"RESEARCH_QUEUE_FULL\"}".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        when(rest.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class))).thenThrow(error);
        JSONObject result = service(rest).submitResearchJob("/api/async/backtest", new JSONObject(), 42L);
        assertEquals("研究任务队列已满，请稍后重试", result.getString("error"));
        assertEquals("RESEARCH_QUEUE_FULL", result.getString("code"));
        assertEquals(429, result.getIntValue("upstream_status"));
    }

    @Test void missingJobKeepsItsExpiryMessage() {
        RestTemplate rest = mock(RestTemplate.class);
        var error = HttpClientErrorException.create(HttpStatus.NOT_FOUND, "expired", HttpHeaders.EMPTY,
                "{\"error\":\"任务不存在或已过期，请重新提交\"}".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        when(rest.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class))).thenThrow(error);
        JSONObject result = service(rest).getResearchJob("expired", 42L);
        assertEquals("任务不存在或已过期，请重新提交", result.getString("error"));
        assertEquals(404, result.getIntValue("upstream_status"));
    }

    @Test void closedRunnerKeepsItsRetryMessage() {
        RestTemplate rest = mock(RestTemplate.class);
        var error = HttpServerErrorException.create(HttpStatus.SERVICE_UNAVAILABLE, "unavailable", HttpHeaders.EMPTY,
                "{\"error\":\"任务服务暂不可用，请稍后重试\"}".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        when(rest.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class))).thenThrow(error);
        JSONObject result = service(rest).submitResearchJob("/api/async/backtest", new JSONObject(), 42L);
        assertEquals("任务服务暂不可用，请稍后重试", result.getString("error"));
        assertEquals(503, result.getIntValue("upstream_status"));
    }

    @Test void malformedUpstreamBodyRetainsTheGenericHandlerAndOtherRoutesAreUnaffected() {
        RestTemplate rest = mock(RestTemplate.class);
        var error = HttpServerErrorException.create(HttpStatus.BAD_GATEWAY, "bad gateway", HttpHeaders.EMPTY,
                "<html>internal failure</html>".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        when(rest.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class))).thenThrow(error);
        when(rest.postForObject(anyString(), any(), eq(String.class))).thenThrow(error);
        DataService service = service(rest);
        assertSame(error, assertThrows(HttpServerErrorException.class,
                () -> service.submitResearchJob("/api/async/backtest", new JSONObject(), 42L)));
        assertSame(error, assertThrows(HttpServerErrorException.class,
                () -> service.runBacktest(new JSONObject())));
    }
}
